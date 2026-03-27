"""Tests for configuration loading."""

import os

import pytest

from holoviz_mcp_server.config import Config, get_config, reset_config


class TestGetConfig:
    def test_default_port(self):
        config = get_config()
        assert config.port == 5077

    def test_default_host(self):
        config = get_config()
        assert config.host == "127.0.0.1"

    def test_default_max_restarts(self):
        config = get_config()
        assert config.max_restarts == 3

    def test_returns_same_instance(self):
        assert get_config() is get_config()

    def test_env_override_port(self, monkeypatch):
        monkeypatch.setenv("HOLOVIZ_MCP_SERVER_PORT", "9999")
        reset_config()
        config = get_config()
        assert config.port == 9999

    def test_env_override_host(self, monkeypatch):
        monkeypatch.setenv("HOLOVIZ_MCP_SERVER_HOST", "0.0.0.0")
        reset_config()
        config = get_config()
        assert config.host == "0.0.0.0"

    def test_env_override_max_restarts(self, monkeypatch):
        monkeypatch.setenv("HOLOVIZ_MCP_SERVER_MAX_RESTARTS", "10")
        reset_config()
        config = get_config()
        assert config.max_restarts == 10

    def test_env_override_db_path(self, monkeypatch, tmp_path):
        db_path = str(tmp_path / "test.db")
        monkeypatch.setenv("HOLOVIZ_MCP_SERVER_DB_PATH", db_path)
        reset_config()
        config = get_config()
        assert str(config.db_path) == db_path


class TestResetConfig:
    def test_reset_creates_new_instance(self):
        first = get_config()
        reset_config()
        second = get_config()
        assert first is not second

    def test_reset_picks_up_new_env_vars(self, monkeypatch):
        get_config()  # prime the singleton
        monkeypatch.setenv("HOLOVIZ_MCP_SERVER_PORT", "8888")
        reset_config()
        assert get_config().port == 8888


class TestConfig:
    def test_db_path_ends_in_db(self):
        config = get_config()
        assert config.db_path.suffix == ".db"

    def test_skills_dir_exists(self):
        config = get_config()
        assert config.skills_dir.exists()
