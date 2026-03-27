"""Panel servable pages."""

from holoviz_mcp_server.display.pages.add_page import add_page
from holoviz_mcp_server.display.pages.admin_page import admin_page
from holoviz_mcp_server.display.pages.feed_page import feed_page
from holoviz_mcp_server.display.pages.view_page import view_page

__all__ = ["add_page", "admin_page", "feed_page", "view_page"]
