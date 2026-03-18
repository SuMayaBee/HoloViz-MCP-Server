"""Server composition — mounts all sub-servers into the main MCP server."""

from holoviz_mcp_app.server.holoviews_mcp import mcp as holoviews_mcp
from holoviz_mcp_app.server.hvplot_mcp import mcp as hvplot_mcp
from holoviz_mcp_app.server.main import mcp as main_mcp
from holoviz_mcp_app.server.panel_mcp import mcp as panel_mcp


def get_composed_server():
    """Set up and return the composed MCP server with all sub-servers mounted."""
    from holoviz_mcp_app.guided.server import mcp as guided_mcp

    # Mount sub-servers with namespaces
    main_mcp.mount(guided_mcp, namespace="viz")
    main_mcp.mount(panel_mcp, namespace="pn")
    main_mcp.mount(hvplot_mcp, namespace="hvplot")
    main_mcp.mount(holoviews_mcp, namespace="hv")

    return main_mcp
