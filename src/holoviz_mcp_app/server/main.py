"""Main MCP server — composes all sub-servers with namespaces.

This is the entry point for the MCP server. It eagerly starts the Panel
display server and exposes all tools via FastMCP composition.
"""

import asyncio
import atexit
import json
import logging
import os
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastmcp import Context
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.apps import AppConfig
from fastmcp.server.apps import ResourceCSP

from holoviz_mcp_app.config import get_config
from holoviz_mcp_app.display.client import DisplayClient
from holoviz_mcp_app.display.manager import PanelServerManager
from holoviz_mcp_app.display.utils import ExtensionError
from holoviz_mcp_app.display.utils import validate_extension_availability
from holoviz_mcp_app.display.validation import SecurityError
from holoviz_mcp_app.display.validation import ValidationError
from holoviz_mcp_app.display.validation import ast_check
from holoviz_mcp_app.display.validation import check_packages
from holoviz_mcp_app.display.validation import ruff_check

logger = logging.getLogger(__name__)

# Global instances
_manager: PanelServerManager | None = None
_client: DisplayClient | None = None
_validation_cache: dict[tuple[str, str], dict] = {}
_fully_validated: set[tuple[str, str]] = set()


def _run_validation(code: str, method: str) -> dict:
    """Run static validation layers and cache the result."""
    key = (code, method)
    if key in _validation_cache:
        return _validation_cache[key]

    result: dict = {}

    if err := ast_check(code):
        result = {"valid": False, "layer": "syntax", "message": err}
    else:
        try:
            ruff_check(code)
        except SecurityError as e:
            result = {"valid": False, "layer": "security", "message": str(e)}

    if not result:
        if err := check_packages(code):
            result = {"valid": False, "layer": "packages", "message": err}

    if not result and method == "panel":
        try:
            validate_extension_availability(code)
        except ExtensionError as e:
            result = {"valid": False, "layer": "extensions", "message": str(e)}

    if not result:
        result = {"valid": True}

    _validation_cache[key] = result
    return result


def _raise_validation_error(validation: dict) -> None:
    layer = validation.get("layer", "")
    message = validation.get("message", "Validation failed.")
    if layer == "security":
        raise SecurityError(message)
    elif layer == "syntax":
        raise ValidationError(f"[syntax] {message}")
    elif layer == "packages":
        raise ValidationError(f"[packages] {message}")
    elif layer == "extensions":
        raise ValidationError(f"[extensions] {message}")
    else:
        raise ValidationError(message)


def _externalize_url(url: str) -> str:
    """Convert local URLs to externally reachable URLs.

    Also normalizes localhost → 127.0.0.1 to avoid IPv6 resolution issues
    in VS Code and other Electron-based clients.
    """
    if not url:
        return url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"localhost", "127.0.0.1"}:
        return url
    external_url = get_config().external_url
    if external_url:
        path = parsed.path or ""
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{external_url.rstrip('/')}{path}{query}"
    # Normalize localhost → 127.0.0.1 to prevent IPv6 issues in VS Code/Electron
    if host == "localhost":
        port_part = f":{parsed.port}" if parsed.port else ""
        path = parsed.path or ""
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{parsed.scheme}://127.0.0.1{port_part}{path}{query}"
    return url


def _render_to_json_item(code: str, method: str) -> dict | None:
    """Render pure HoloViews/hvPlot code to a Bokeh JSON spec for client-side embedding.

    Only works for HoloViews/hvPlot objects — Panel widgets with custom models
    require the live Panel server URL instead (they cannot be serialized to pure Bokeh JSON).
    Returns a json_item dict or None if not applicable / rendering fails.
    """
    try:
        import holoviews as hv
        import panel as pn
        from bokeh.embed import json_item

        from holoviz_mcp_app.display.utils import execute_in_module
        from holoviz_mcp_app.display.utils import extract_last_expression

        if method != "jupyter":
            # Panel .servable() code always uses Panel custom models — use server URL
            return None

        preamble = "import panel as pn\npn.config.design = None\n\n"
        full_code = preamble + code

        statements, last_expr = extract_last_expression(full_code)
        namespace = execute_in_module(statements, module_name="html_render_module", cleanup=False)
        if not last_expr:
            return None
        result = eval(last_expr, namespace)  # noqa: S307
        if result is None:
            return None

        # Unwrap Panel HoloViews pane to get the underlying HV object
        if isinstance(result, pn.pane.HoloViews):
            result = result.object

        # Only serialize pure HoloViews/hvPlot objects — these produce clean Bokeh figures
        # with no Panel custom models, so BokehJS can render them without Panel's JS bundles.
        if not isinstance(result, hv.core.Dimensioned):
            return None

        hv.extension("bokeh")
        bokeh_fig = hv.render(result, backend="bokeh")
        bokeh_fig.sizing_mode = "stretch_width"
        return json_item(bokeh_fig, "chart-container")

    except Exception as e:
        logger.debug(f"json_item rendering failed: {e}")
        return None
    finally:
        sys.modules.pop("html_render_module", None)



def _start_panel_server() -> tuple[PanelServerManager | None, DisplayClient | None]:
    """Start the Panel server subprocess and create a client."""
    config = get_config()
    manager = PanelServerManager(
        db_path=config.db_path,
        port=config.port,
        host=config.host,
        max_restarts=config.max_restarts,
    )
    if not manager.start():
        logger.error("Failed to start Panel server")
        return None, None
    client = DisplayClient(base_url=manager.get_base_url())
    return manager, client


_cleaned_up = False


def _cleanup():
    global _manager, _client, _cleaned_up
    if _cleaned_up:
        return
    _cleaned_up = True
    if _client:
        _client.close()
        _client = None
    if _manager:
        _manager.stop()
        _manager = None


def _sigterm_handler(signum, frame):
    _cleanup()
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    os.kill(os.getpid(), signal.SIGTERM)


signal.signal(signal.SIGTERM, _sigterm_handler)


@asynccontextmanager
async def app_lifespan(app):
    """MCP server lifespan — eagerly start the Panel server."""
    global _manager, _client

    logger.info("Starting HoloViz MCP App...")
    _manager, _client = _start_panel_server()

    if _manager:
        atexit.register(_cleanup)
        feed_url = _externalize_url(f"http://{_manager.host}:{_manager.port}/feed")
        print(f"\n  HoloViz MCP App is running.\n  Feed: {feed_url}\n", file=sys.stderr, flush=True)  # noqa: T201
        logger.info(f"Panel server started — feed: {feed_url}")
    else:
        logger.warning("Panel server failed to start — show tool will not work")

    try:
        yield
    finally:
        _cleanup()


# --- Main MCP Server ---

mcp = FastMCP(
    "HoloViz MCP App",
    instructions=(
        "HoloViz MCP App creates interactive visualizations and dashboards using Panel, hvPlot, and HoloViews.\n\n"
        "TOOLS:\n"
        "- show(code): Execute Python code and render as live interactive visualization\n"
        "- stream(code): Execute streaming Panel code with periodic callbacks\n"
        "- load_data(source): Profile a dataset (columns, types, sample values)\n"
        "- handle_interaction(...): Called by MCP App when user clicks a chart point\n"
        "- skill_list/skill_get: Access best-practice guides for Panel, hvPlot, HoloViews\n"
        "- viz.create/viz.dashboard: High-level guided tools (no Python needed)\n"
        "- pn.list/pn.get/pn.params/pn.search: Panel component introspection\n"
        "- hvplot.list/hvplot.get: hvPlot plot type discovery\n"
        "- hv.list/hv.get: HoloViews element discovery\n\n"
        "LIBRARY PREFERENCE: hvPlot > HoloViews > Panel > Matplotlib > Plotly > Bokeh\n\n"
        "After show(), always present the URL as a clickable Markdown link: [Open visualization](url)\n"
        "In VS Code: the link opens in Simple Browser inside the editor."
    ),
    lifespan=app_lifespan,
)


# --- MCP App Resources (templates for inline rendering in Claude Desktop) ---

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
VIZ_RESOURCE_URI = "ui://holoviz-mcp-app/viz"
STREAM_RESOURCE_URI = "ui://holoviz-mcp-app/stream"


_RESOURCE_CSP = ResourceCSP(
    resource_domains=[
        "https://cdn.bokeh.org",
        "https://unpkg.com",
        "https://*.basemaps.cartocdn.com",
        "https://*.tile.openstreetmap.org",
    ],
    frame_domains=[
        "http://127.0.0.1:5077",
        "http://localhost:5077",
    ],
)


@mcp.resource(VIZ_RESOURCE_URI, app=AppConfig(csp=_RESOURCE_CSP))
def viz_app_resource() -> str:
    """Serve the visualization template for MCP Apps rendering."""
    return (_TEMPLATES_DIR / "show.html").read_text()


@mcp.resource(STREAM_RESOURCE_URI, app=AppConfig(csp=_RESOURCE_CSP))
def stream_app_resource() -> str:
    """Serve the stream template for MCP Apps rendering."""
    return (_TEMPLATES_DIR / "stream.html").read_text()


# --- Core Tools ---

@mcp.tool(name="show", app=AppConfig(resource_uri=VIZ_RESOURCE_URI))
async def show(
    code: str,
    name: str = "",
    description: str = "",
    method: Literal["jupyter", "panel"] = "jupyter",
    zoom: int = 100,
    quick: bool = True,
    ctx: Context | None = None,
) -> str:
    """Display Python code as a live, interactive visualization.

    Parameters
    ----------
    code : str
        Python code to execute.
        For "jupyter": last expression is displayed.
        For "panel": call .servable() on objects.
    name : str
        Short descriptive name for the visualization.
    description : str
        One-sentence description.
    method : str
        "jupyter" (last expr displayed) or "panel" (.servable()).
    zoom : int
        Zoom level: 25, 50, 75, or 100.
    quick : bool
        If True, run full validation inline.
    """
    global _manager, _client

    _valid_zooms = [25, 50, 75, 100]
    zoom = min(_valid_zooms, key=lambda z: abs(z - zoom))

    if quick:
        validation = _run_validation(code, method)
        if not validation["valid"]:
            _raise_validation_error(validation)

        from holoviz_mcp_app.display.utils import validate_code

        runtime_error = await asyncio.to_thread(validate_code, code)
        if runtime_error:
            raise ValidationError(f"[runtime] {runtime_error}")
    else:
        key = (code, method)
        if key not in _fully_validated:
            raise ValidationError("Code not validated. Call validate() first or use quick=True.")
        validation = _run_validation(code, method)
        if not validation["valid"]:
            _raise_validation_error(validation)

    if not _client:
        config = get_config()
        raise ToolError(f"Panel server not running. Ensure port {config.port} is available.")

    if not _client.is_healthy():
        if ctx:
            await ctx.info("Panel server unhealthy, attempting restart...")
        if _manager and _manager.restart():
            _client.close()
            _client = DisplayClient(base_url=_manager.get_base_url())
        else:
            raise ToolError("Panel server unhealthy and restart failed.")

    try:
        response = _client.create_snippet(
            code=code, name=name, description=description, method=method,
        )
        url = _externalize_url(response.get("url", ""))

        if error_message := response.get("error_message", None):
            raise ToolError(f"Visualization created but failed at runtime:\n{error_message}")

        # Try json_item for pure HoloViews/hvPlot (no Panel custom models needed)
        figure_spec = await asyncio.to_thread(_render_to_json_item, code, method)

        if figure_spec:
            # HoloViews/hvPlot chart — rendered client-side by BokehJS
            result = {
                "action": "create",
                "figure": figure_spec,
                "url": url,
                "name": name or "Visualization",
                "viz_id": response.get("id", ""),
            }
        else:
            # Panel widget code — load live Panel server URL in iframe
            result = {
                "action": "panel_url",
                "url": url,
                "name": name or "Visualization",
                "viz_id": response.get("id", ""),
            }

        return json.dumps(result)

    except (SecurityError, ValidationError):
        raise
    except (SyntaxError, ExtensionError) as e:
        raise ValidationError(str(e)) from e
    except ValueError as e:
        raise ValidationError(f"[packages] {e}") from e
    except Exception as e:
        logger.exception(f"Error creating visualization: {e}")
        raise ToolError(f"Failed to create visualization: {e!s}") from e


@mcp.tool(name="stream", app=AppConfig(resource_uri=STREAM_RESOURCE_URI))
async def stream(
    code: str,
    name: str = "",
    description: str = "",
    ctx: Context | None = None,
) -> str:
    """Execute streaming Panel code with periodic callbacks.

    The code should use pn.state.add_periodic_callback() for real-time updates.
    This runs server-side in the Panel subprocess — real data sources work.

    Parameters
    ----------
    code : str
        Panel code using .servable() and periodic callbacks.
    name : str
        Name for the stream.
    description : str
        Description of what the stream shows.
    """
    global _client

    validation = _run_validation(code, "panel")
    if not validation["valid"]:
        _raise_validation_error(validation)

    if not _client:
        raise ToolError("Panel server not running.")

    try:
        response = _client.create_snippet(
            code=code, name=name, description=description, method="panel",
        )
        url = _externalize_url(response.get("url", ""))

        return json.dumps({
            "url": url,
            "name": name or "Stream",
            "viz_id": response.get("id", ""),
        })

    except Exception as e:
        raise ToolError(f"Failed to create stream: {e!s}") from e


@mcp.tool(name="load_data")
async def load_data(
    source: str,
    ctx: Context | None = None,
) -> str:
    """Profile a dataset — returns column names, dtypes, nulls, sample values, shape.

    Supports: CSV, TSV, Parquet, Arrow, JSON, JSONL, Excel, Zarr, remote URLs (s3://, https://).
    The LLM then writes show(code) where the code reads the same source.

    Parameters
    ----------
    source : str
        File path or URL to the dataset.
    """
    import pandas as pd

    try:
        source_lower = source.lower()

        if source_lower.endswith(".parquet"):
            df = pd.read_parquet(source)
        elif source_lower.endswith((".json", ".jsonl")):
            df = pd.read_json(source, lines=source_lower.endswith(".jsonl"))
        elif source_lower.endswith((".xls", ".xlsx")):
            df = pd.read_excel(source)
        elif source_lower.endswith(".tsv"):
            df = pd.read_csv(source, sep="\t")
        elif source_lower.endswith(".zarr"):
            import xarray as xr

            ds = xr.open_zarr(source)
            df = ds.to_dataframe().reset_index()
        else:
            df = pd.read_csv(source)

        profile = {
            "source": source,
            "shape": {"rows": len(df), "columns": len(df.columns)},
            "columns": [],
        }

        for col in df.columns:
            col_info = {
                "name": col,
                "dtype": str(df[col].dtype),
                "nulls": int(df[col].isna().sum()),
                "unique": int(df[col].nunique()),
                "sample": [str(v) for v in df[col].head(3).tolist()],
            }
            if df[col].dtype in ("int64", "float64"):
                col_info["min"] = float(df[col].min())
                col_info["max"] = float(df[col].max())
                col_info["mean"] = float(df[col].mean())
            profile["columns"].append(col_info)

        return json.dumps(profile)

    except Exception as e:
        return json.dumps({"error": str(e), "source": source})


@mcp.tool(name="handle_interaction", app=AppConfig(resource_uri=VIZ_RESOURCE_URI, visibility=["app"]))
async def handle_interaction(
    viz_id: str,
    x_value: str = "",
    y_value: float = 0.0,
    point_index: int = 0,
    ctx: Context | None = None,
) -> str:
    """Handle click events from MCP App when user clicks a chart point.

    Called by the MCP App (not the LLM). Computes insight from the data.

    Parameters
    ----------
    viz_id : str
        Visualization/snippet ID.
    x_value : str
        X-axis value of clicked point.
    y_value : float
        Y-axis value of clicked point.
    point_index : int
        Index of the clicked data point.
    """
    return json.dumps({
        "action": "insight",
        "message": f"Point {point_index}: {x_value} = {y_value}",
        "viz_id": viz_id,
    })


@mcp.tool(name="validate")
async def validate(
    code: str,
    method: Literal["jupyter", "panel"] = "jupyter",
    ctx: Context | None = None,
) -> dict:
    """Validate Python visualization code — run before show().

    Checks: syntax, security, packages, extensions, runtime execution.
    """
    from holoviz_mcp_app.display.utils import validate_code

    result = _run_validation(code, method)
    if not result["valid"]:
        return result

    error = await asyncio.to_thread(validate_code, code)
    if error:
        return {"valid": False, "layer": "runtime", "message": error}

    _fully_validated.add((code, method))
    return {"valid": True}


@mcp.tool(name="skill_list")
async def skill_list(ctx: Context | None = None) -> list[dict[str, str]]:
    """List all available agent skills (best-practice guides)."""
    from holoviz_mcp_app.core.skills import list_skills

    return list_skills()


@mcp.tool(name="skill_get")
async def skill_get(name: str, ctx: Context | None = None) -> str:
    """Get a specific skill by name.

    Parameters
    ----------
    name : str
        Skill name (e.g., 'panel', 'hvplot', 'holoviews').
    """
    from holoviz_mcp_app.core.skills import get_skill

    return get_skill(name)


@mcp.tool(name="list_packages")
async def list_packages(
    category: str = "core",
    query: str = "",
    ctx: Context | None = None,
) -> list[str]:
    """List Python packages installed in the server environment.

    Parameters
    ----------
    category : str
        Filter: "visualization", "data", "panel", "core", or "" for all.
    query : str
        Substring filter on package name.
    """
    from importlib.metadata import distributions

    _CATEGORIES: dict[str, set[str]] = {
        "visualization": {"bokeh", "holoviews", "hvplot", "matplotlib", "panel", "plotly", "seaborn", "altair", "datashader"},
        "data": {"numpy", "pandas", "polars", "pyarrow", "scipy", "xarray", "duckdb"},
        "panel": {"panel", "param", "pyviz-comms"},
    }
    _CATEGORIES["core"] = _CATEGORIES["visualization"] | _CATEGORIES["data"] | _CATEGORIES["panel"]

    pkgs = sorted(
        (dist.metadata["Name"] for dist in distributions()),
        key=lambda n: n.lower(),
    )

    if category:
        allowed = set()
        for cat in category.split(","):
            cat = cat.strip().lower()
            if cat in _CATEGORIES:
                allowed |= _CATEGORIES[cat]
        if allowed:
            pkgs = [p for p in pkgs if p.lower().replace("_", "-") in allowed]

    if query:
        query_lower = query.lower()
        pkgs = [p for p in pkgs if query_lower in p.lower()]

    return pkgs
