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

from holoviz_mcp_server.config import get_config
from holoviz_mcp_server.display.client import DisplayClient
from holoviz_mcp_server.display.manager import PanelServerManager
from holoviz_mcp_server.utils import ExtensionError
from holoviz_mcp_server.utils import validate_extension_availability
from holoviz_mcp_server.validation import SecurityError
from holoviz_mcp_server.validation import ValidationError
from holoviz_mcp_server.validation import ast_check
from holoviz_mcp_server.validation import check_packages
from holoviz_mcp_server.validation import ruff_check

logger = logging.getLogger(__name__)

# Global instances
_manager: PanelServerManager | None = None
_client: DisplayClient | None = None
_validation_cache: dict[tuple[str, str], dict] = {}
_fully_validated: set[tuple[str, str]] = set()

# In-memory store for guided-tool visualizations (enables update/theme/annotate/export)
_viz_store: dict[str, dict] = {}


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

        from holoviz_mcp_server.utils import execute_in_module
        from holoviz_mcp_server.utils import extract_last_expression

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
        print(f"\n  HoloViz MCP App is running.\n  Feed: {feed_url}\n", file=sys.stderr, flush=True)
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
        "ENVIRONMENT NOTES:\n"
        "- All required packages are pre-installed — NEVER suggest pip install, pixi install, or pixi remove commands\n"
        "- If a package is missing, use list_packages() to check what IS available and rewrite the code accordingly\n\n"
        "PANEL LAYOUT NOTES:\n"
        "- NEVER use sizing_mode='stretch_both' on pn.Column or top-level layouts — causes huge empty gaps between components\n"
        "- Use sizing_mode='stretch_width' instead; only set explicit height on chart/plot panes\n\n"
        "CHART TYPE NOTES:\n"
        "- hvPlot does NOT support pie/donut charts — use Bokeh figure.wedge() with cumsum() transform instead\n"
        "- For pie charts: from bokeh.transform import cumsum; df['angle'] = df[col]/df[col].sum()*2*3.14159; p.wedge(...)\n"
        "- For gauge/radial/polar charts: use Bokeh or Matplotlib, not hvPlot\n"
        "- For tile maps (OpenStreetMap, CartoDB): use df.hvplot.points(geo=True, tiles='OSM') — NEVER import bokeh.tile_providers (removed in Bokeh 3.x)\n\n"
        "After show(), always present the URL as a clickable Markdown link: [Open visualization](url)\n"
        "In VS Code: the link opens in Simple Browser inside the editor."
    ),
    lifespan=app_lifespan,
)


# --- MCP App Resources (templates for inline rendering in Claude Desktop) ---

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
VIZ_RESOURCE_URI = "ui://holoviz-mcp-server/viz-v9"
STREAM_RESOURCE_URI = "ui://holoviz-mcp-server/stream"
DASHBOARD_RESOURCE_URI = "ui://holoviz-mcp-server/dashboard-v2"


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


@mcp.resource(DASHBOARD_RESOURCE_URI, app=AppConfig(csp=_RESOURCE_CSP))
def dashboard_app_resource() -> str:
    """Serve the dashboard template for MCP Apps rendering."""
    return (_TEMPLATES_DIR / "dashboard.html").read_text()


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

        from holoviz_mcp_server.utils import validate_code

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
        # Lazily try to connect if the server started after MCP server initialization
        config = get_config()
        _lazy_client = DisplayClient(base_url=f"http://{config.host}:{config.port}")
        if _lazy_client.is_healthy():
            _client = _lazy_client
        else:
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
            code=code,
            name=name,
            description=description,
            method=method,
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
                "code": code,
            }
        else:
            # Panel widget code — load live Panel server URL in iframe
            result = {
                "action": "panel_url",
                "url": url,
                "name": name or "Visualization",
                "viz_id": response.get("id", ""),
                "code": code,
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
            code=code,
            name=name,
            description=description,
            method="panel",
        )
        url = _externalize_url(response.get("url", ""))

        return json.dumps(
            {
                "url": url,
                "name": name or "Stream",
                "viz_id": response.get("id", ""),
            }
        )

    except Exception as e:
        raise ToolError(f"Failed to create stream: {e!s}") from e


def _resolve_kaggle_source(source: str) -> str | dict:
    """Download a Kaggle dataset/competition and return the local file path.

    Returns a file path string on success, or an error dict if credentials are
    missing or the download fails.
    """
    import re
    import tempfile

    username = os.environ.get("KAGGLE_USERNAME")
    key = os.environ.get("KAGGLE_KEY")

    if not username or not key:
        return {
            "error": (
                "Kaggle API credentials not provided. "
                "Add KAGGLE_USERNAME and KAGGLE_KEY to the env section of your MCP config:\n"
                '  "env": { "KAGGLE_USERNAME": "your_username", "KAGGLE_KEY": "your_api_key" }\n'
                "Get your API key at https://www.kaggle.com → Account → Settings → Create New Token."
            ),
            "source": source,
        }

    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = key

    try:
        import kaggle  # noqa: PLC0415
    except ImportError:
        return {"error": "kaggle package is not installed. Reinstall with the 'kaggle' extra: uvx --from \"holoviz-mcp-server[kaggle]\" hvmcp mcp", "source": source}

    download_dir = tempfile.mkdtemp(prefix="holoviz_kaggle_")

    # Dataset URL: kaggle.com/datasets/owner/name
    dataset_match = re.search(r"kaggle\.com/datasets/([^/?#]+/[^/?#]+)", source)
    # Competition URL: kaggle.com/competitions/name
    competition_match = re.search(r"kaggle\.com/competitions/([^/?#]+)", source)

    try:
        if dataset_match:
            slug = dataset_match.group(1)
            kaggle.api.authenticate()
            kaggle.api.dataset_download_files(slug, path=download_dir, unzip=True)
        elif competition_match:
            slug = competition_match.group(1)
            kaggle.api.authenticate()
            kaggle.api.competition_download_files(slug, path=download_dir)
        else:
            return {"error": f"Could not parse Kaggle URL: {source}", "source": source}
    except Exception as e:
        return {"error": f"Kaggle download failed: {e}", "source": source}

    # Find the first CSV or Parquet file in the download directory
    for ext in ("*.csv", "*.parquet", "*.tsv", "*.json"):
        matches = list(Path(download_dir).rglob(ext))
        if matches:
            return str(matches[0])

    return {"error": "No CSV/Parquet/TSV/JSON file found in the downloaded Kaggle dataset.", "source": source}


def _resolve_huggingface_source(source: str) -> str | dict:
    """Download a HuggingFace dataset and return the local file path.

    Returns a file path string on success, or an error dict on failure.
    HF_TOKEN env var is optional — only needed for private datasets.
    """
    import re
    import tempfile

    match = re.search(r"huggingface\.co/datasets/([^/?#]+/[^/?#]+)", source)
    if not match:
        return {"error": f"Could not parse HuggingFace dataset URL: {source}", "source": source}

    repo_id = match.group(1)
    token = os.environ.get("HF_TOKEN")  # optional

    try:
        from huggingface_hub import list_repo_files  # noqa: PLC0415
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
    except ImportError:
        return {"error": "huggingface_hub package is not installed. Reinstall with the 'huggingface' extra: uvx --from \"holoviz-mcp-server[huggingface]\" hvmcp mcp", "source": source}

    try:
        download_dir = tempfile.mkdtemp(prefix="holoviz_hf_")
        # Find the first Parquet or CSV file in the dataset repo
        all_files = list(list_repo_files(repo_id, repo_type="dataset", token=token))
        target = next(
            (f for f in all_files if f.endswith(".parquet")),
            next((f for f in all_files if f.endswith(".csv")), None),
        )
        if not target:
            return {"error": f"No Parquet or CSV file found in HuggingFace dataset '{repo_id}'.", "source": source}

        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=target,
            repo_type="dataset",
            token=token,
            local_dir=download_dir,
        )
        return local_path

    except Exception as e:
        return {"error": f"HuggingFace download failed: {e}", "source": source}


def _recommend_charts(profile: dict) -> list[dict]:
    """Analyse a dataset profile and return up to 3 chart recommendations with ready-to-run code."""
    source = profile["source"]
    rows = profile["shape"]["rows"]
    columns = profile["columns"]

    numeric_cols = [c["name"] for c in columns if c["dtype"] in ("int64", "float64", "int32", "float32")]
    categorical_cols = [c["name"] for c in columns if c["dtype"] in ("object", "category", "bool") and c["unique"] < 50]
    datetime_cols = [
        c["name"]
        for c in columns
        if "datetime" in c["dtype"] or any(k in c["name"].lower() for k in ("date", "time", "year", "month"))
    ]

    # Use datashade=True for large datasets automatically
    large = rows > 100_000
    datashade_arg = ", datashade=True" if large else ""

    # Detect file reader
    src_lower = source.lower()
    if src_lower.endswith(".parquet"):
        reader = f'pd.read_parquet("{source}")'
    elif src_lower.endswith(".tsv"):
        reader = f'pd.read_csv("{source}", sep="\\t")'
    else:
        reader = f'pd.read_csv("{source}")'

    recs: list[dict] = []

    # 1. Time series line chart
    if datetime_cols and numeric_cols:
        t, v = datetime_cols[0], numeric_cols[0]
        recs.append({
            "type": "line",
            "title": f"{v} over time",
            "reason": f"Datetime column '{t}' + numeric column '{v}' detected",
            "code": (
                f"import pandas as pd\nimport hvplot.pandas\n"
                f'df = {reader}\ndf["{t}"] = pd.to_datetime(df["{t}"])\n'
                f'df.hvplot.line(x="{t}", y="{v}"{datashade_arg}, title="{v} over time")'
            ),
        })

    # 2. Scatter for numeric pairs
    if len(numeric_cols) >= 2:
        x, y = numeric_cols[0], numeric_cols[1]
        color_arg = f', by="{categorical_cols[0]}"' if categorical_cols else ""
        recs.append({
            "type": "scatter",
            "title": f"{x} vs {y}",
            "reason": f"Two numeric columns '{x}' and '{y}' detected",
            "code": (
                f"import pandas as pd\nimport hvplot.pandas\n"
                f"df = {reader}\n"
                f'df.hvplot.scatter(x="{x}", y="{y}"{color_arg}{datashade_arg}, title="{x} vs {y}")'
            ),
        })

    # 3. Bar for categorical + numeric
    if categorical_cols and numeric_cols:
        cat, val = categorical_cols[0], numeric_cols[0]
        recs.append({
            "type": "bar",
            "title": f"{val} by {cat}",
            "reason": f"Categorical column '{cat}' + numeric column '{val}' detected",
            "code": (
                f"import pandas as pd\nimport hvplot.pandas\n"
                f"df = {reader}\n"
                f'df.groupby("{cat}")["{val}"].mean().hvplot.bar(title="{val} by {cat}", rot=45)'
            ),
        })

    # 4. Histogram fallback
    if len(recs) < 3 and numeric_cols:
        val = numeric_cols[0]
        recs.append({
            "type": "histogram",
            "title": f"Distribution of {val}",
            "reason": f"Numeric column '{val}' available for distribution analysis",
            "code": (
                f"import pandas as pd\nimport hvplot.pandas\n"
                f"df = {reader}\n"
                f'df.hvplot.hist("{val}", bins=30, title="Distribution of {val}")'
            ),
        })

    return recs[:3]


@mcp.tool(name="load_data")
async def load_data(
    source: str,
    ctx: Context | None = None,
) -> str:
    """Profile a dataset — returns column names, dtypes, nulls, sample values, shape.

    Supports: CSV, TSV, Parquet, Arrow, JSON, JSONL, Excel, Zarr, remote URLs (s3://, https://),
    and Kaggle dataset/competition URLs (requires KAGGLE_USERNAME + KAGGLE_KEY in env).
    The LLM then writes show(code) where the code reads the same source.

    Parameters
    ----------
    source : str
        File path, URL, or Kaggle dataset/competition URL to the dataset.
    """
    import pandas as pd

    try:
        # Resolve Kaggle URLs before any other processing
        if "kaggle.com" in source.lower():
            result = _resolve_kaggle_source(source)
            if isinstance(result, dict):
                return json.dumps(result)
            source = result  # local file path

        # Resolve HuggingFace dataset URLs
        elif "huggingface.co/datasets" in source.lower():
            result = _resolve_huggingface_source(source)
            if isinstance(result, dict):
                return json.dumps(result)
            source = result  # local file path

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

        rows = len(df)
        profile = {
            "source": source,
            "shape": {"rows": rows, "columns": len(df.columns)},
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

        # Auto chart recommendations based on column types
        profile["recommendations"] = _recommend_charts(profile)

        # Flag large datasets so the LLM knows to use datashader
        if rows > 100_000:
            profile["large_dataset"] = True
            profile["datashader_note"] = (
                f"Dataset has {rows:,} rows. Use datashade=True in hvplot calls for performance. "
                "Example: df.hvplot.scatter(x='col1', y='col2', datashade=True)"
            )

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
    return json.dumps(
        {
            "action": "insight",
            "message": f"Point {point_index}: {x_value} = {y_value}",
            "viz_id": viz_id,
        }
    )


@mcp.tool(name="validate")
async def validate(
    code: str,
    method: Literal["jupyter", "panel"] = "jupyter",
    ctx: Context | None = None,
) -> dict:
    """Validate Python visualization code — run before show().

    Checks: syntax, security, packages, extensions, runtime execution.
    """
    from holoviz_mcp_server.utils import validate_code

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
    from holoviz_mcp_server.introspection.skills import list_skills

    return list_skills()


@mcp.tool(name="skill_get")
async def skill_get(name: str, ctx: Context | None = None) -> str:
    """Get a specific skill by name.

    Parameters
    ----------
    name : str
        Skill name (e.g., 'panel', 'hvplot', 'holoviews').
    """
    from holoviz_mcp_server.introspection.skills import get_skill

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
        "visualization": {
            "bokeh",
            "holoviews",
            "hvplot",
            "matplotlib",
            "panel",
            "plotly",
            "seaborn",
            "altair",
            "datashader",
        },
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


@mcp.tool(name="update_viz", app=AppConfig(resource_uri=VIZ_RESOURCE_URI))
async def update_viz(
    viz_id: str,
    kind: str | None = None,
    title: str | None = None,
    data: dict[str, list] | None = None,
    x: str | None = None,
    y: str | None = None,
    color: str | None = None,
    ctx: Context | None = None,
) -> str:
    """Update an existing visualization created by viz.create. Only provide fields to change.

    Parameters
    ----------
    viz_id : str
        ID returned in the original viz.create response.
    kind : str
        New chart type (bar, line, scatter, area, pie, histogram, box, violin, kde, step, heatmap, hexbin).
    title : str
        New chart title.
    data : dict
        Replacement data as {column_name: [values]}.
    x : str
        New x-axis column.
    y : str
        New y-axis column.
    color : str
        New color-grouping column. Pass empty string to remove.
    """
    import pandas as pd

    from holoviz_mcp_server.chart_builders import rebuild_figure

    if viz_id not in _viz_store:
        return json.dumps(
            {
                "action": "error",
                "message": f"Visualization '{viz_id}' not found. Only charts created by viz.create support update_viz.",
            }
        )

    viz = _viz_store[viz_id]
    if kind is not None:
        viz["kind"] = kind
    if title is not None:
        viz["title"] = title
    if data is not None:
        viz["data"] = data
    if x is not None:
        viz["x"] = x
    if y is not None:
        viz["y"] = y
    if color is not None:
        viz["color"] = color if color != "" else None

    cols = list(pd.DataFrame(viz["data"]).columns)
    if viz["x"] not in cols:
        return json.dumps({"action": "error", "message": f"Column '{viz['x']}' not found. Available: {cols}"})
    if viz["y"] not in cols:
        return json.dumps({"action": "error", "message": f"Column '{viz['y']}' not found. Available: {cols}"})

    try:
        spec = rebuild_figure(viz)
        return json.dumps({"action": "update", "id": viz_id, "figure": spec})
    except Exception as e:
        return json.dumps({"action": "error", "message": str(e)})


@mcp.tool(name="set_theme", app=AppConfig(resource_uri=VIZ_RESOURCE_URI, visibility=["app"]))
async def set_theme(
    viz_id: str,
    theme: str = "dark",
    ctx: Context | None = None,
) -> str:
    """Switch visualization between dark and light theme with proper Bokeh re-rendering.

    Parameters
    ----------
    viz_id : str
        ID of the visualization to re-theme.
    theme : str
        "dark" or "light".
    """
    from holoviz_mcp_server.chart_builders import rebuild_figure

    if theme not in ("dark", "light"):
        return json.dumps({"action": "error", "message": "Theme must be 'dark' or 'light'"})
    if viz_id not in _viz_store:
        return json.dumps({"action": "theme_change", "id": viz_id, "theme": theme})

    viz = _viz_store[viz_id]
    viz["theme"] = theme

    try:
        spec = rebuild_figure(viz)
        return json.dumps({"action": "theme_change", "id": viz_id, "theme": theme, "figure": spec})
    except Exception as e:
        return json.dumps({"action": "error", "message": str(e)})


@mcp.tool(name="annotate_viz", app=AppConfig(resource_uri=VIZ_RESOURCE_URI))
async def annotate_viz(
    viz_id: str,
    annotation_type: str,
    config: dict,
    ctx: Context | None = None,
) -> str:
    """Add an annotation to an existing visualization (reference lines, bands, text, arrows).

    Parameters
    ----------
    viz_id : str
        ID of the visualization to annotate.
    annotation_type : str
        One of: hline, vline, text, band, arrow.
    config : dict
        hline: {y_value, color?, dash?, label?}
        vline: {x_value, color?, dash?}
        text:  {x, y, text, color?, font_size?}
        band:  {lower, upper, color?, alpha?}
        arrow: {x_start, y_start, x_end, y_end, color?}
    """
    from holoviz_mcp_server.chart_builders import ANNOTATION_TYPES
    from holoviz_mcp_server.chart_builders import rebuild_figure

    if annotation_type not in ANNOTATION_TYPES:
        return json.dumps({"action": "error", "message": f"Unsupported annotation type. Use: {ANNOTATION_TYPES}"})
    if viz_id not in _viz_store:
        return json.dumps(
            {
                "action": "error",
                "message": f"Viz '{viz_id}' not found. Only charts from viz.create support annotations.",
            }
        )

    viz = _viz_store[viz_id]
    viz.setdefault("annotations", []).append({"type": annotation_type, "config": config})

    try:
        spec = rebuild_figure(viz)
        return json.dumps({"action": "update", "id": viz_id, "figure": spec})
    except Exception as e:
        return json.dumps({"action": "error", "message": str(e)})


@mcp.tool(name="export_data", app=AppConfig(resource_uri=VIZ_RESOURCE_URI))
async def export_data(
    viz_id: str,
    format: str = "csv",
    ctx: Context | None = None,
) -> str:
    """Export the data behind a visualization as CSV or JSON.

    Parameters
    ----------
    viz_id : str
        ID of the visualization to export.
    format : str
        "csv" or "json".
    """
    import pandas as pd

    if viz_id not in _viz_store:
        return json.dumps(
            {
                "action": "error",
                "message": f"Viz '{viz_id}' not found. Only charts from viz.create support data export.",
            }
        )

    viz = _viz_store[viz_id]
    if "data" not in viz:
        return json.dumps({"action": "error", "message": "No data available for this visualization."})

    df = pd.DataFrame(viz["data"])

    if format == "csv":
        data_str = df.to_csv(index=False)
    elif format == "json":
        data_str = df.to_json(orient="records", indent=2)
    else:
        return json.dumps({"action": "error", "message": "Format must be 'csv' or 'json'"})

    safe_title = viz["title"].replace(" ", "_").lower()
    return json.dumps(
        {
            "action": "export",
            "id": viz_id,
            "format": format,
            "data": data_str,
            "filename": f"{safe_title}.{format}",
        }
    )


@mcp.tool(name="apply_filter", app=AppConfig(resource_uri=DASHBOARD_RESOURCE_URI, visibility=["app"]))
async def apply_filter(
    viz_id: str,
    filters: dict,
    ctx: Context | None = None,
) -> str:
    """Apply filters to a dashboard. Called by the dashboard UI widgets.

    Parameters
    ----------
    viz_id : str
        ID of the dashboard visualization.
    filters : dict
        {column: value} for categorical (use "__all__" to clear),
        {column: [min, max]} for numeric range.
    """
    import pandas as pd

    from holoviz_mcp_server.chart_builders import build_bokeh_figure

    if viz_id not in _viz_store:
        return json.dumps({"action": "error", "message": f"Dashboard '{viz_id}' not found."})

    viz = _viz_store[viz_id]
    df = pd.DataFrame(viz["data"])

    for col, value in filters.items():
        if col not in df.columns:
            continue
        if value == "__all__":
            continue
        if isinstance(value, str):
            df = df[df[col] == value]
        elif isinstance(value, list) and len(value) == 2:
            df = df[(df[col] >= value[0]) & (df[col] <= value[1])]

    if df.empty:
        return json.dumps({
            "action": "filter_result", "id": viz_id,
            "empty": True, "message": "No data matches the current filters",
        })

    theme = viz.get("theme", "dark")
    spec = build_bokeh_figure(
        viz["kind"], df, viz["x"], viz["y"], viz["title"], viz.get("color"),
        target_id=viz.get("target_id", "chart"), theme=theme,
    )

    y_series = pd.to_numeric(df[viz["y"]], errors="coerce").dropna()
    stats = {
        "count": int(y_series.count()),
        "mean": round(float(y_series.mean()), 2),
        "median": round(float(y_series.median()), 2),
        "min": round(float(y_series.min()), 2),
        "max": round(float(y_series.max()), 2),
        "std": round(float(y_series.std()), 2) if len(y_series) > 1 else 0.0,
        "sum": round(float(y_series.sum()), 2),
    }

    max_table_rows = 200
    return json.dumps({
        "action": "filter_result",
        "id": viz_id,
        "empty": False,
        "figure": spec,
        "stats": stats,
        "table": {
            "columns": list(df.columns),
            "rows": df.head(max_table_rows).values.tolist(),
            "total": len(df),
        },
        "filtered_rows": len(df),
    })
