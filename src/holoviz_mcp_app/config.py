"""Configuration for HoloViz MCP App."""

import logging
import os
from pathlib import Path

from pydantic import BaseModel
from pydantic import Field

logger = logging.getLogger("holoviz_mcp_app")


def _default_user_dir() -> Path:
    return Path(os.getenv("HOLOVIZ_MCP_APP_USER_DIR", "~/.holoviz-mcp-app")).expanduser()


def _resolve_external_url(port: int) -> str:
    """Resolve the external URL for the Panel server.

    Checks in priority order:
    1. HOLOVIZ_MCP_APP_EXTERNAL_URL — explicit override
    2. JUPYTERHUB_HOST + JUPYTERHUB_SERVICE_PREFIX — JupyterHub
    3. CODESPACE_NAME — GitHub Codespaces
    4. "" — local fallback
    """
    if explicit := os.getenv("HOLOVIZ_MCP_APP_EXTERNAL_URL", ""):
        return explicit.rstrip("/")

    hub_host = os.getenv("JUPYTERHUB_HOST", "")
    hub_prefix = os.getenv("JUPYTERHUB_SERVICE_PREFIX", "")
    if hub_host and hub_prefix:
        if not hub_host.startswith(("http://", "https://")):
            hub_host = f"https://{hub_host}"
        return f"{hub_host.rstrip('/')}{hub_prefix}proxy/{port}"

    if codespace := os.getenv("CODESPACE_NAME", ""):
        domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN") or "app.github.dev"
        return f"https://{codespace}-{port}.{domain}"

    return ""


class Config(BaseModel):
    """HoloViz MCP App configuration."""

    port: int = Field(default=5077, description="Port for the Panel server")
    host: str = Field(default="127.0.0.1", description="Host address for the Panel server")
    max_restarts: int = Field(default=3, description="Maximum number of restart attempts")
    db_path: Path = Field(
        default_factory=lambda: _default_user_dir() / "snippets" / "snippets.db",
        description="Path to SQLite database for snippets",
    )
    external_url: str = Field(
        default="",
        description="Externally reachable base URL for the Panel server.",
    )
    skills_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent / "skills",
        description="Path to built-in skills directory",
    )


_config: Config | None = None


def get_config() -> Config:
    """Get or create the config instance."""
    global _config
    if _config is None:
        port = int(os.getenv("HOLOVIZ_MCP_APP_PORT", "5077"))
        _config = Config(
            port=port,
            host=os.getenv("HOLOVIZ_MCP_APP_HOST", "127.0.0.1"),
            max_restarts=int(os.getenv("HOLOVIZ_MCP_APP_MAX_RESTARTS", "3")),
            db_path=Path(
                os.getenv("HOLOVIZ_MCP_APP_DB_PATH", str(_default_user_dir() / "snippets" / "snippets.db"))
            ),
            external_url=_resolve_external_url(port),
        )
    return _config


def reset_config() -> None:
    """Reset config (for testing)."""
    global _config
    _config = None
