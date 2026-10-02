"""Tests for config loading, including .env file support (no real secrets).

All tests monkeypatch _env_file_candidates so the developer's real .env in the
project root is never picked up - the suite must stay offline and hermetic.
"""

from __future__ import annotations

import pytest

from protrainup_mcp import config as config_mod
from protrainup_mcp.config import (
    ENV_LOGIN,
    ENV_PASSWORD,
    TransportConfig,
    load_config,
    load_transport_config,
)

ENV_KEYS = (
    "PROTRAINUP_LOGIN",
    "PROTRAINUP_PASSWORD",
    "PROTRAINUP_BASE_URL",
    "PROTRAINUP_TIMEOUT",
    "PROTRAINUP_MCP_TRANSPORT",
    "PROTRAINUP_MCP_HOST",
    "PROTRAINUP_MCP_PORT",
)


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch, tmp_path):
    """No env vars, and .env lookup points only at the empty tmp dir."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config_mod, "_env_file_candidates", lambda: [tmp_path / ".env"])


def test_missing_credentials_when_no_env_and_no_file():
    config = load_config()
    assert config.login == ""
    assert config.password == ""
    assert not config.has_credentials


def test_env_file_values_are_loaded(tmp_path):
    (tmp_path / ".env").write_text(
        "# komentarz\n"
        "PROTRAINUP_LOGIN=coach@example.com\n"
        'PROTRAINUP_PASSWORD="sup er tajne"\n',
        encoding="utf-8",
    )
    config = load_config()
    assert config.login == "coach@example.com"
    assert config.password == "sup er tajne"
    assert config.has_credentials


def test_process_environment_wins_over_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_LOGIN, "from-shell")
    monkeypatch.setenv(ENV_PASSWORD, "from-shell-pass")
    (tmp_path / ".env").write_text(
        "PROTRAINUP_LOGIN=from-file\nPROTRAINUP_PASSWORD=from-file-pass\n",
        encoding="utf-8",
    )
    config = load_config()
    assert config.login == "from-shell"
    assert config.password == "from-shell-pass"


def test_env_file_keys_must_not_leak_into_os_environ(tmp_path):
    import os

    (tmp_path / ".env").write_text("PROTRAINUP_LOGIN=x\n", encoding="utf-8")
    load_config()
    assert ENV_LOGIN not in os.environ


def test_trailing_quote_in_password_is_preserved(tmp_path):
    (tmp_path / ".env").write_text('PROTRAINUP_PASSWORD=abc"def\n', encoding="utf-8")
    assert load_config().password == 'abc"def'


def test_matched_quote_pair_is_stripped(tmp_path):
    (tmp_path / ".env").write_text('PROTRAINUP_PASSWORD="abc def"\n', encoding="utf-8")
    assert load_config().password == "abc def"


class TestTransportConfig:
    def test_defaults_to_stdio(self):
        t = load_transport_config()
        assert t == TransportConfig(transport="stdio", host="127.0.0.1", port=8000)
        assert not t.is_http

    def test_http_env_enables_http_with_container_default_host(self, monkeypatch):
        monkeypatch.setenv("PROTRAINUP_MCP_TRANSPORT", "http")
        t = load_transport_config()
        assert t.is_http
        assert t.host == "0.0.0.0"
        assert t.port == 8000

    def test_streamable_http_alias_is_accepted(self, monkeypatch):
        monkeypatch.setenv("PROTRAINUP_MCP_TRANSPORT", "streamable-http")
        assert load_transport_config().is_http

    def test_host_and_port_from_env(self, monkeypatch):
        monkeypatch.setenv("PROTRAINUP_MCP_TRANSPORT", "http")
        monkeypatch.setenv("PROTRAINUP_MCP_HOST", "127.0.0.1")
        monkeypatch.setenv("PROTRAINUP_MCP_PORT", "9001")
        t = load_transport_config()
        assert (t.host, t.port) == ("127.0.0.1", 9001)

    def test_invalid_transport_raises(self, monkeypatch):
        monkeypatch.setenv("PROTRAINUP_MCP_TRANSPORT", "grpc")
        with pytest.raises(ValueError, match="stdio.*http|PROTRAINUP_MCP_TRANSPORT"):
            load_transport_config()

    def test_transport_knobs_read_from_env_file(self, tmp_path):
        (tmp_path / ".env").write_text(
            "PROTRAINUP_MCP_TRANSPORT=http\nPROTRAINUP_MCP_PORT=8123\n",
            encoding="utf-8",
        )
        t = load_transport_config()
        assert t.is_http
        assert t.port == 8123
