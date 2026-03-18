"""HoloViz MCP App — MCP server for the HoloViz ecosystem."""

try:
    from importlib.metadata import version

    __version__ = version("holoviz-mcp-app")
except Exception:
    __version__ = "0.1.0"
