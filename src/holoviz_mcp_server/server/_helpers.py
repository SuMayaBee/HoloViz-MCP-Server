"""Private helper functions for the main MCP server.

Rendering, URL rewriting, and validation logic extracted from main.py.
"""

from __future__ import annotations

import functools
import logging
import sys
from urllib.parse import urlparse

from holoviz_mcp_server.utils import ExtensionError
from holoviz_mcp_server.utils import validate_extension_availability
from holoviz_mcp_server.validation import SecurityError
from holoviz_mcp_server.validation import ValidationError
from holoviz_mcp_server.validation import ast_check
from holoviz_mcp_server.validation import check_packages
from holoviz_mcp_server.validation import ruff_check

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=256)
def run_validation(code: str, method: str) -> dict:
    """Run static validation layers. Results are cached (LRU, max 256 entries)."""
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

    return result


def raise_validation_error(validation: dict) -> None:
    """Convert a validation result dict into the appropriate exception."""
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


def externalize_url(url: str) -> str:
    """Convert local URLs to externally reachable URLs.

    Also normalizes localhost → 127.0.0.1 to avoid IPv6 resolution issues
    in VS Code and other Electron-based clients.
    """
    if not url:
        return url

    from holoviz_mcp_server.config import get_config

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


def render_to_json_item(code: str, method: str) -> dict | None:
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

        if isinstance(result, pn.pane.HoloViews):
            result = result.object

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
