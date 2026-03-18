"""HoloViews element introspection sub-server (namespace: hv)."""

from fastmcp import Context
from fastmcp import FastMCP

mcp = FastMCP("HoloViews")


@mcp.tool(name="list")
async def hv_list(ctx: Context | None = None) -> list[dict[str, str]]:
    """List all available HoloViews elements (Curve, Scatter, Points, etc.)."""
    from holoviz_mcp_app.core.hv import list_elements

    return list_elements()


@mcp.tool(name="get")
async def hv_get(
    name: str,
    backend: str = "bokeh",
    ctx: Context | None = None,
) -> str:
    """Get documentation for a HoloViews element.

    Parameters
    ----------
    name : str
        Element name (e.g., 'Curve', 'Scatter', 'Points').
    backend : str
        Backend for options: 'bokeh', 'matplotlib', 'plotly'.
    """
    from holoviz_mcp_app.core.hv import get_element

    return get_element(name, backend=backend)
