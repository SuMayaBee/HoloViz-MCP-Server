"""hvPlot plot type introspection sub-server (namespace: hvplot)."""

from fastmcp import Context
from fastmcp import FastMCP

mcp = FastMCP("hvPlot")


@mcp.tool(name="list")
async def hvplot_list(ctx: Context | None = None) -> list[dict[str, str]]:
    """List all available hvPlot plot types (bar, line, scatter, etc.)."""
    from holoviz_mcp_app.core.hvplot import list_plot_types

    return list_plot_types()


@mcp.tool(name="get")
async def hvplot_get(
    name: str,
    info: str = "docstring",
    ctx: Context | None = None,
) -> str:
    """Get documentation or signature for a specific hvPlot plot type.

    Parameters
    ----------
    name : str
        Plot type name (e.g., 'bar', 'line', 'scatter').
    info : str
        'docstring' or 'signature'.
    """
    from holoviz_mcp_app.core.hvplot import get_plot_type

    return get_plot_type(name, info=info)
