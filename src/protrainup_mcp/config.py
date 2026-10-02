"""Configuration loaded from the environment and an optional local .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://api.protrainup.com"

ENV_LOGIN = "PROTRAINUP_LOGIN"
ENV_PASSWORD = "PROTRAINUP_PASSWORD"
ENV_BASE_URL = "PROTRAINUP_BASE_URL"
ENV_TIMEOUT = "PROTRAINUP_TIMEOUT"
ENV_MCP_TRANSPORT = "PROTRAINUP_MCP_TRANSPORT"
ENV_MCP_HOST = "PROTRAINUP_MCP_HOST"
ENV_MCP_PORT = "PROTRAINUP_MCP_PORT"

_ENV_KEYS = (
    ENV_LOGIN,
    ENV_PASSWORD,
    ENV_BASE_URL,
    ENV_TIMEOUT,
    ENV_MCP_TRANSPORT,
    ENV_MCP_HOST,
    ENV_MCP_PORT,
)


def _env_file_candidates() -> list[Path]:
    """Where to look for a .env file: current directory, then project root."""
    return [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]


def _env_file_overrides() -> dict[str, str]:
    """Read PROTRAINUP_* values from a .env file.

    Lets the user keep credentials out of shell/chat. Real environment
    variables always win; values are never logged or echoed anywhere.
    """
    overrides: dict[str, str] = {}
    for path in _env_file_candidates():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # strip quotes only as a matched pair, so a password that merely
            # ends with a quote character survives intact
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key in _ENV_KEYS and key not in os.environ:
                overrides[key] = value
        break
    return overrides


@dataclass(frozen=True)
class Config:
    login: str
    password: str
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 30.0

    @property
    def has_credentials(self) -> bool:
        return bool(self.login) and bool(self.password)


def load_config() -> Config:
    overrides = _env_file_overrides()

    def get(key: str, default: str = "") -> str:
        return os.environ.get(key) or overrides.get(key, default)

    try:
        timeout = float(get(ENV_TIMEOUT, "30"))
    except ValueError:
        timeout = 30.0
    return Config(
        login=get(ENV_LOGIN),
        password=get(ENV_PASSWORD),
        base_url=get(ENV_BASE_URL, DEFAULT_BASE_URL).rstrip("/"),
        timeout=timeout,
    )


@dataclass(frozen=True)
class TransportConfig:
    """How the MCP server itself listens (independent of ProTrainUp credentials)."""

    transport: str = "stdio"  # "stdio" | "http"
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def is_http(self) -> bool:
        return self.transport == "http"


def load_transport_config() -> TransportConfig:
    overrides = _env_file_overrides()

    def get(key: str, default: str = "") -> str:
        return os.environ.get(key) or overrides.get(key, default)

    transport = get(ENV_MCP_TRANSPORT, "stdio").strip().lower()
    if transport in ("http", "streamable-http", "streamable_http"):
        transport = "http"
    elif transport != "stdio":
        raise ValueError(
            f"{ENV_MCP_TRANSPORT} must be 'stdio' or 'http', got: {transport!r}"
        )
    try:
        port = int(get(ENV_MCP_PORT, "8000"))
    except ValueError:
        port = 8000
    return TransportConfig(
        transport=transport,
        host=get(ENV_MCP_HOST, "127.0.0.1" if transport == "stdio" else "0.0.0.0"),
        port=port,
    )
