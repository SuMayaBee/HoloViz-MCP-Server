"""Panel component introspection sub-server (namespace: pn)."""

from fastmcp import Context
from fastmcp import FastMCP

mcp = FastMCP("Panel Components")


@mcp.tool(name="list")
async def pn_list(
    category: str = "",
    ctx: Context | None = None,
) -> list[dict[str, str]]:
    """List Panel components (widgets, panes, layouts).

    Parameters
    ----------
    category : str
        Filter by category: "widget", "pane", "layout", or "" for all.
    """
    from holoviz_mcp_server.introspection.panel import list_components

    return list_components(category=category or None)


@mcp.tool(name="get")
async def pn_get(
    name: str,
    ctx: Context | None = None,
) -> dict:
    """Get detailed information about a Panel component.

    Parameters
    ----------
    name : str
        Component name (e.g., 'Button', 'Tabulator', 'FastListTemplate').
    """
    from holoviz_mcp_server.introspection.panel import get_component

    return get_component(name)


@mcp.tool(name="params")
async def pn_params(
    name: str,
    ctx: Context | None = None,
) -> dict:
    """Get parameter details for a Panel component.

    Parameters
    ----------
    name : str
        Component name.
    """
    from holoviz_mcp_server.introspection.panel import get_component_params

    return get_component_params(name)


@mcp.tool(name="search")
async def pn_search(
    query: str,
    limit: int = 10,
    ctx: Context | None = None,
) -> list[dict]:
    """Search Panel components by name or description.

    Parameters
    ----------
    query : str
        Search query.
    limit : int
        Maximum results.
    """
    from holoviz_mcp_server.introspection.panel import search_components

    return search_components(query, limit=limit)
