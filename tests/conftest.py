"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def reset_config():
    """Reset the config singleton before each test."""
    from holoviz_mcp_server.config import reset_config as _reset
    _reset()
    yield
    _reset()
