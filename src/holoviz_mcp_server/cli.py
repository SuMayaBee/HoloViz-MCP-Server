"""CLI for HoloViz MCP App."""

import logging
import os
import sys
from typing import Annotated

if sys.platform == "win32":
    from holoviz_mcp_server.utils import prepend_env_dll_paths

    prepend_env_dll_paths(os.environ)

import typer

from holoviz_mcp_server import __version__

logger = logging.getLogger(__name__)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"holoviz-mcp-server {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="hvmcp",
    help="HoloViz MCP App — interactive visualizations and dashboards via MCP.",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", "-V", callback=version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """HoloViz MCP App — interactive visualizations and dashboards via MCP."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def serve(
    port: int = typer.Option(5077, "--port", "-p", help="Port for Panel server.", envvar="HOLOVIZ_MCP_SERVER_PORT"),
    host: str = typer.Option("localhost", "--host", "-H", help="Host address.", envvar="HOLOVIZ_MCP_SERVER_HOST"),
    db_path: str | None = typer.Option(
        None, "--db-path", help="SQLite database path.", envvar="HOLOVIZ_MCP_SERVER_DB_PATH"
    ),
    show: bool = typer.Option(False, "--show", help="Open in browser."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
) -> None:
    """Start the Panel visualization server directly."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    os.environ["HOLOVIZ_MCP_SERVER_PORT"] = str(port)
    os.environ["HOLOVIZ_MCP_SERVER_HOST"] = host
    if db_path:
        os.environ["HOLOVIZ_MCP_SERVER_DB_PATH"] = db_path

    from holoviz_mcp_server.config import reset_config

    reset_config()

    from holoviz_mcp_server.display.app import main as app_main

    try:
        app_main(address=host, port=port, show=show)
    except OSError as exc:
        import errno

        if exc.errno != errno.EADDRINUSE:
            raise
        typer.echo(f"Error: port {port} is already in use.", err=True)
        typer.echo(f"  Try: hvmcp serve --port {port + 1}", err=True)
        raise typer.Exit(1) from None


@app.command()
def mcp(
    transport: str = typer.Option("stdio", "--transport", "-t", help="MCP transport: stdio, http, or sse."),
    host: str = typer.Option("127.0.0.1", "--host", help="Host for HTTP/SSE transport."),
    port: int = typer.Option(8001, "--port", "-p", help="Port for HTTP/SSE transport."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
) -> None:
    """Start as an MCP server for AI assistants."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    from holoviz_mcp_server.server.compose import get_composed_server

    mcp_server = get_composed_server()

    if transport == "stdio":
        mcp_server.run(transport="stdio")
    elif transport == "http":
        mcp_server.run(transport="streamable-http", host=host, port=port)
    elif transport == "sse":
        mcp_server.run(transport="sse", host=host, port=port)
    else:
        typer.echo(f"Unknown transport: {transport!r}. Choose: stdio, http, sse.")
        raise typer.Exit(1)


@app.command()
def status(
    port: int = typer.Option(5077, "--port", "-p", envvar="HOLOVIZ_MCP_SERVER_PORT"),
    host: str = typer.Option("localhost", "--host", "-H", envvar="HOLOVIZ_MCP_SERVER_HOST"),
) -> None:
    """Check whether the Panel server is running."""
    import requests

    url = f"http://{host}:{port}/api/health"
    try:
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            typer.echo(f"Running  http://{host}:{port}/feed  (healthy at {data.get('timestamp', '?')})")
        else:
            typer.echo(f"Unhealthy  (status {resp.status_code})")
            raise typer.Exit(1)
    except requests.ConnectionError:
        typer.echo(f"Not running  (nothing on {host}:{port})")
        raise typer.Exit(1) from None
    except requests.Timeout:
        typer.echo("Timeout  (no response within 3s)")
        raise typer.Exit(1) from None


def main() -> None:
    """Entry point for the hvmcp command."""
    app()


if __name__ == "__main__":
    main()
