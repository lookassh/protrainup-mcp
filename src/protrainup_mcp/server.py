"""MCP server exposing read-only ProTrainUp tools for AI agents.

Run (stdio transport, the default for MCP clients):

    protrainup-mcp

Requires PROTRAINUP_LOGIN and PROTRAINUP_PASSWORD in the environment.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import httpx

from mcp.server.mcpserver import MCPServer

from .client import ProTrainUpClient, ProTrainUpError
from .config import load_config
from .web import WebSessionClient

mcp = MCPServer("protrainup", instructions=(
    "Read-only access to a ProTrainUp club account through the unofficial "
    "mobile API (Laravel + JWT). Start with ptu_whoami to verify the account. "
    "ptu_calendar needs a date range. Use ptu_api_get to explore further GET "
    "endpoints. All tools fail with a clear message when credentials are "
    "missing or rejected."
))

_client: ProTrainUpClient | None = None
_web_client: WebSessionClient | None = None
_client_lock = threading.Lock()
_web_client_lock = threading.Lock()


def _get_client() -> ProTrainUpClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = ProTrainUpClient(load_config())
    return _client


def _get_web_client() -> WebSessionClient:
    global _web_client
    if _web_client is None:
        with _web_client_lock:
            if _web_client is None:
                _web_client = WebSessionClient(load_config())
    return _web_client


def _run(call) -> str:
    try:
        result = call()
    except ProTrainUpError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    except httpx.HTTPError as exc:
        return json.dumps({"error": f"network error: {exc}"}, ensure_ascii=False)
    except ValueError as exc:
        # e.g. malformed params_json from the agent
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, default=str)


def _parse_params(params_json: str | None) -> dict[str, Any]:
    if not params_json or not params_json.strip():
        return {}
    try:
        params = json.loads(params_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"params_json is not valid JSON: {exc}") from exc
    if not isinstance(params, dict):
        raise ValueError("params_json must be a JSON object, e.g. '{\"month\": \"2026-10\"}'")
    return params


@mcp.tool()
def ptu_whoami() -> str:
    """Verify ProTrainUp credentials and return the logged-in account (GET /api/auth/me)."""
    return _run(lambda: _get_client().whoami())


@mcp.tool()
def ptu_user(user_id: int) -> str:
    """Return a ProTrainUp user profile by id (GET /api/users/{id}).

    Includes name, e-mail, avatar and profile details. Ids of related people
    can be found in ptu_whoami (created_by) or calendar data.
    """
    return _run(lambda: _get_client().user(user_id))


@mcp.tool()
def ptu_calendar(from_date: str, to_date: str) -> str:
    """Return club calendar events for a date range (GET /api/calendar).

    Dates in YYYY-MM-DD format, e.g. ptu_calendar("2026-10-01", "2026-10-31").
    Each event has a type ("training", match, ...), title, start/end, location
    and an oid/u_code pair identifying it.
    """
    return _run(lambda: _get_client().calendar(from_date, to_date))


@mcp.tool()
def ptu_tests(test_id: int = 0) -> str:
    """List motoric test definitions (GET /api/tests), or one test when test_id > 0.

    Each test has a name (e.g. 10m_run), category and measurement units.
    """
    return _run(lambda: _get_client().tests(test_id=test_id or None))


@mcp.tool()
def ptu_exercises() -> str:
    """List exercises (GET /api/exercises); may be empty for some clubs."""
    return _run(lambda: _get_client().exercises())


@mcp.tool()
def ptu_conversations() -> str:
    """List all message conversations (GET /api/conversation).

    Each conversation includes participants with unread counters and the
    users (name, surname) - use ids with ptu_messages to read the history.
    """
    return _run(lambda: _get_client().conversations())


@mcp.tool()
def ptu_messages(conversation_id: int) -> str:
    """Read the full message history of one conversation.

    conversation_id comes from ptu_conversations. Returns conversation
    metadata plus messages (author user_id, text, created_at, isSender).
    """
    def call():
        conversation = _get_client().conversation(conversation_id, with_messages=True)
        messages = conversation.get("messages", []) if isinstance(conversation, dict) else []
        summary = {
            "conversation_id": conversation_id,
            "topic": conversation.get("topic") if isinstance(conversation, dict) else None,
            "users": {
                u.get("id"): f'{u.get("name")} {u.get("surname")}'
                for u in (conversation.get("users") or [])
            }
            if isinstance(conversation, dict)
            else {},
            "count": len(messages),
            "messages": messages,
        }
        return summary

    return _run(call)


@mcp.tool()
def ptu_stream_posts(stream_id: int, stream: str = "team", page: int = 0) -> str:
    """Read the club wall / activity stream (web session route, read-only).

    stream: "team" with the team id (e.g. 1234) or "announcements" with the
    club announcements scope id (e.g. 5678); "user"/"group" also exist,
    "club"/"organization" need higher permissions.
    Posts embed author, html content, files, comments, likes and pinInfo.
    """
    return _run(lambda: _get_web_client().stream_posts(stream_id, stream, page))


@mcp.tool()
def ptu_scheduled_posts(stream_id: int, stream: str = "team") -> str:
    """List posts scheduled for future publication on a team stream (read-only)."""
    return _run(lambda: _get_web_client().scheduled_posts(stream_id, stream))


@mcp.tool()
def ptu_events_list(from_date: str, to_date: str, event_filter: str = "all") -> str:
    """Calendar events for a date range, richer than ptu_calendar (web route).

    Dates in YYYY-MM-DD. Adds staff (coach), team_name, location_full and a
    preview uri per event. Types: training / match / event.
    """
    return _run(lambda: _get_web_client().events_list(from_date, to_date, event_filter))


@mcp.tool()
def ptu_diary_files() -> str:
    """Team disk file tree (web route /pl/diary/files/open, read-only).

    Folders with nested files: name, creator, size, date. Documents shared
    with the team by the club.
    """
    return _run(lambda: _get_web_client().diary_files())


@mcp.tool()
def ptu_api_get(path: str, params_json: str = "") -> str:
    """Perform an authenticated read-only GET against any ProTrainUp API path.

    The API is undocumented, so this lets the agent explore it safely with a
    valid token. path is used as-is when it starts with '/', otherwise it is
    appended to '/api/'. Only GET is performed - never writes.

    Examples: path="events", path="/api/events/12".
    """
    normalized = path if path.startswith("/") else f"/api/{path.lstrip('/')}"
    return _run(lambda: _get_client().get(normalized, params=_parse_params(params_json)))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
