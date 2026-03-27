"""Panel server for code visualization.

Entry point for the Panel subprocess that serves web pages and REST endpoints.
"""

import logging
from urllib.parse import urlparse

from holoviz_mcp_server.config import get_config
from holoviz_mcp_server.display.endpoints import HealthEndpoint
from holoviz_mcp_server.display.endpoints import SnippetEndpoint

logger = logging.getLogger(__name__)


def _build_websocket_origins(address: str, port: int) -> list[str]:
    origins: set[str] = {
        f"localhost:{port}",
        f"127.0.0.1:{port}",
    }
    if address and address not in {"0.0.0.0", "::"}:
        origins.add(f"{address}:{port}")

    external_url = get_config().external_url
    if external_url:
        parsed = urlparse(external_url)
        if parsed.hostname:
            if parsed.port:
                origins.add(f"{parsed.hostname}:{parsed.port}")
            else:
                origins.add(parsed.hostname)
                if parsed.scheme == "https":
                    origins.add(f"{parsed.hostname}:443")
                elif parsed.scheme == "http":
                    origins.add(f"{parsed.hostname}:80")

    return sorted(origins)


def main(address: str = "localhost", port: int = 5077, show: bool = True) -> None:
    """Start the Panel server."""
    import panel as pn

    from holoviz_mcp_server.display.database import get_db
    from holoviz_mcp_server.display.pages import view_page

    _ = get_db()

    pn.template.FastListTemplate.param.main_layout.default = None
    pn.pane.Markdown.param.disable_anchors.default = True
    pn.state.cache["views"] = {}

    pages = {"/view": view_page}

    extra_patterns = [
        (r"/api/snippet", SnippetEndpoint),
        (r"/api/health", HealthEndpoint),
    ]

    logger.info(f"Starting HoloViz MCP App server at http://{address}:{port}")

    pn.serve(
        pages,
        port=port,
        address=address,
        show=show,
        title="HoloViz MCP App",
        extra_patterns=extra_patterns,
        websocket_origin=_build_websocket_origins(address=address, port=port),
    )


if __name__ == "__main__":
    from holoviz_mcp_server.config import reset_config

    reset_config()
    config = get_config()
    main(address=config.host, port=config.port, show=False)
