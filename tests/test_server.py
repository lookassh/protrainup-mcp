"""Server-level tests that need no network: tool registration and helpers."""

from __future__ import annotations

import asyncio
import json

import pytest

from protrainup_mcp import server


def tool_names() -> list[str]:
    return [tool.name for tool in asyncio.run(server.mcp.list_tools())]


def test_expected_tools_are_registered():
    assert set(tool_names()) == {
        "ptu_whoami",
        "ptu_user",
        "ptu_calendar",
        "ptu_tests",
        "ptu_exercises",
        "ptu_conversations",
        "ptu_messages",
        "ptu_stream_posts",
        "ptu_scheduled_posts",
        "ptu_events_list",
        "ptu_diary_files",
        "ptu_api_get",
    }


def test_parse_params_accepts_empty_and_objects():
    assert server._parse_params("") == {}
    assert server._parse_params(None) == {}
    assert server._parse_params('{"month": "2026-10"}') == {"month": "2026-10"}


def test_parse_params_rejects_non_object_json():
    with pytest.raises(ValueError, match="JSON object"):
        server._parse_params("[1, 2]")


def test_parse_params_rejects_invalid_json():
    with pytest.raises(ValueError, match="not valid JSON"):
        server._parse_params("{nope}")


def test_whoami_without_credentials_returns_error_json(monkeypatch, tmp_path):
    import os

    from protrainup_mcp import config as config_mod

    monkeypatch.setattr(config_mod, "_env_file_candidates", lambda: [tmp_path / ".env"])
    saved = {k: os.environ.pop(k, None) for k in ("PROTRAINUP_LOGIN", "PROTRAINUP_PASSWORD")}
    try:
        result = json.loads(server.ptu_whoami())
        assert "PROTRAINUP_LOGIN" in result["error"]
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value


def test_network_error_reaches_agent_as_json(monkeypatch, tmp_path):
    import httpx

    from protrainup_mcp import config as config_mod
    from protrainup_mcp.client import ProTrainUpClient

    def raising_handler(request):
        raise httpx.ConnectError("connection refused by test")

    monkeypatch.setattr(config_mod, "_env_file_candidates", lambda: [tmp_path / ".env"])
    original = server._client
    server._client = ProTrainUpClient(
        config_mod.Config(login="x", password="y"), transport=httpx.MockTransport(raising_handler)
    )
    try:
        result = json.loads(server.ptu_api_get("events"))
        assert result["error"].startswith("network error:")
    finally:
        server._client = original


def test_malformed_params_json_reaches_agent_as_json(monkeypatch, tmp_path):
    import httpx

    from protrainup_mcp import config as config_mod
    from protrainup_mcp.client import ProTrainUpClient

    monkeypatch.setattr(config_mod, "_env_file_candidates", lambda: [tmp_path / ".env"])
    # dummy client: _parse_params must raise before any HTTP happens
    server._client = ProTrainUpClient(
        config_mod.Config(login="x", password="y"),
        transport=httpx.MockTransport(lambda request: None),
    )
    try:
        result = json.loads(server.ptu_api_get("events", params_json="{nie-json"))
        assert "not valid JSON" in result["error"]
    finally:
        server._client = None


def test_api_get_path_normalization(monkeypatch, tmp_path):
    import httpx

    from protrainup_mcp import config as config_mod
    from protrainup_mcp.client import ProTrainUpClient

    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json=[1])

    monkeypatch.setattr(config_mod, "_env_file_candidates", lambda: [tmp_path / ".env"])
    original = server._client
    client = ProTrainUpClient(
        config_mod.Config(login="x", password="y"),
        transport=httpx.MockTransport(handler),
    )
    client._token = "jwt-test"  # skip login
    server._client = client
    try:
        json.loads(server.ptu_api_get("events"))
        json.loads(server.ptu_api_get("/api/users/5"))
        assert seen == ["/api/events", "/api/users/5"]
    finally:
        server._client = original
