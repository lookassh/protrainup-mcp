"""Offline tests for the web-session client (stream routes)."""

from __future__ import annotations

import json

import httpx
import pytest

from protrainup_mcp.config import Config
from protrainup_mcp.web import WebSessionClient

LOGIN_HTML = '<form method="post" action="/en/login"><input type="hidden" name="_token" value="csrf-123"></form>'
PANEL_HTML = '<html><head><meta name="csrf-token" content="csrf-post-1"></head><body>panel</body></html>'


def panel_handler(stream_response=None, events_response=None, diary_response=None, state=None):
    """Handler covering login + panel CSRF + the three web data routes."""
    state = state if state is not None else {}
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/en/login" and request.method == "GET":
            return httpx.Response(200, text=LOGIN_HTML)
        if request.url.path == "/en/login" and request.method == "POST":
            return httpx.Response(302, headers={"Location": "https://api.test/pl"})
        if request.url.path == "/pl" and request.method == "GET":
            return httpx.Response(200, text=PANEL_HTML)
        if request.url.path == "/pl/stream/posts":
            return httpx.Response(200, json=stream_response if stream_response is not None else [])
        if request.url.path == "/pl/events/list" and request.method == "POST":
            state.setdefault("events_calls", []).append(
                {"form": request.content.decode(), "csrf": request.headers.get("x-csrf-token"),
                 "query": dict(request.url.params)}
            )
            return httpx.Response(200, json=events_response if events_response is not None else [])
        if request.url.path == "/pl/diary/files/open":
            return httpx.Response(200, json=diary_response if diary_response is not None else [])
        raise AssertionError(f"unexpected {request.method} {request.url.path}")
    return handler


class TestEventsList:
    def test_posts_start_end_with_csrf(self):
        state = {}
        client = make_web_client(panel_handler(events_response=[{"type": "training"}], state=state))
        result = client.events_list("2026-10-01", "2026-10-31")
        assert result == [{"type": "training"}]
        call = state["events_calls"][0]
        assert call["form"] == "start=2026-10-01&end=2026-10-31"
        assert call["csrf"] == "csrf-post-1"
        assert call["query"] == {"f": "all"}

    def test_419_refreshes_csrf_and_retries(self):
        panel_fetches = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/en/login" and request.method == "GET":
                return httpx.Response(200, text=LOGIN_HTML)
            if request.url.path == "/en/login" and request.method == "POST":
                return httpx.Response(302, headers={"Location": "https://api.test/pl"})
            if request.url.path == "/pl":
                panel_fetches.append(1)
                token = "csrf-post-1" if len(panel_fetches) == 1 else "csrf-post-2"
                return httpx.Response(200, text=f'<meta name="csrf-token" content="{token}">')
            if request.url.path == "/pl/events/list":
                if request.headers.get("x-csrf-token") == "csrf-post-1":
                    return httpx.Response(419, json={"message": "Token Mismatch"})
                return httpx.Response(200, json=[{"ok": True}])
            raise AssertionError(f"unexpected {request.url.path}")

        client = make_web_client(handler)
        assert client.events_list("2026-10-01", "2026-10-31") == [{"ok": True}]
        assert len(panel_fetches) == 2

    def test_post_401_relogins_and_retries(self):
        logins = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal logins
            if request.url.path == "/en/login" and request.method == "GET":
                return httpx.Response(200, text=LOGIN_HTML)
            if request.url.path == "/en/login" and request.method == "POST":
                logins += 1
                return httpx.Response(302, headers={"Location": "https://api.test/pl"})
            if request.url.path == "/pl":
                return httpx.Response(200, text=PANEL_HTML)
            if request.url.path == "/pl/events/list":
                if logins == 0:
                    return httpx.Response(401, json={"message": "Unauthenticated."})
                return httpx.Response(200, json=[{"ok": True}])
            raise AssertionError(f"unexpected {request.url.path}")

        client = make_web_client(handler)
        client._logged_in = True  # skip initial login so the first POST sees 401
        assert client.events_list("2026-10-01", "2026-10-31") == [{"ok": True}]
        assert logins == 1


class TestDiaryFiles:
    def test_diary_files_tree(self):
        tree = [{"id": "dysk-zespolu", "type": "folder", "data": [{"id": "_file_1", "value": "regulamin.pdf"}]}]
        client = make_web_client(panel_handler(diary_response=tree))
        assert client.diary_files() == tree


def make_web_client(handler) -> WebSessionClient:
    config = Config(login="coach@example.com", password="secret", base_url="https://api.test")
    return WebSessionClient(config, transport=httpx.MockTransport(handler))


class TestWebLogin:
    def test_login_posts_csrf_and_username_field(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/en/login" and request.method == "GET":
                return httpx.Response(200, text=LOGIN_HTML)
            if request.url.path == "/en/login" and request.method == "POST":
                seen["form"] = dict(pair.split("=", 1) for pair in request.content.decode().split("&"))
                return httpx.Response(302, headers={"Location": "https://api.test/pl"})
            raise AssertionError(f"unexpected {request.method} {request.url.path}")

        client = make_web_client(handler)
        client.login()
        assert seen["form"]["_token"] == "csrf-123"
        assert seen["form"]["username"] == "coach%40example.com"
        assert seen["form"]["password"] == "secret"

    def test_wrong_credentials_redirect_back_to_login(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(200, text=LOGIN_HTML)
            return httpx.Response(302, headers={"Location": "https://api.test/en/login"})

        client = make_web_client(handler)
        with pytest.raises(Exception, match="Web login failed"):
            client.login()

    def test_missing_credentials_fail_fast(self):
        with pytest.raises(Exception, match="PROTRAINUP_LOGIN"):
            WebSessionClient(Config(login="", password=""))

    def test_login_form_rerendered_200_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/en/login" and request.method == "GET":
                return httpx.Response(200, text=LOGIN_HTML)
            # wrong credentials answered by re-rendering the form (200, no redirect)
            return httpx.Response(200, text='<input type="password" name="password" required>')

        client = make_web_client(handler)
        with pytest.raises(Exception, match="re-rendered"):
            client.login()


class TestStream:
    def test_stream_posts_auto_logs_in_and_passes_params(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/en/login" and request.method == "GET":
                return httpx.Response(200, text=LOGIN_HTML)
            if request.url.path == "/en/login" and request.method == "POST":
                return httpx.Response(302, headers={"Location": "https://api.test/pl"})
            if request.url.path == "/pl/stream/posts":
                assert dict(request.url.params) == {"stream": "team", "streamId": "1234", "page": "0"}
                return httpx.Response(200, json=[{"id": 520282, "html": "<p>hej</p>"}])
            raise AssertionError(f"unexpected {request.method} {request.url.path}")

        client = make_web_client(handler)
        posts = client.stream_posts(1234)
        assert posts[0]["id"] == 520282
        assert requests[-1].url.path == "/pl/stream/posts"

    def test_scheduled_posts_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/en/login" and request.method == "GET":
                return httpx.Response(200, text=LOGIN_HTML)
            if request.url.path == "/en/login" and request.method == "POST":
                return httpx.Response(302, headers={"Location": "https://api.test/pl"})
            if request.url.path == "/pl/stream/scheduled-posts":
                return httpx.Response(200, json=[])
            raise AssertionError(f"unexpected {request.url.path}")

        client = make_web_client(handler)
        assert client.scheduled_posts(1234) == []

    def test_401_triggers_single_relogin(self):
        logins = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal logins
            if request.url.path == "/en/login" and request.method == "GET":
                return httpx.Response(200, text=LOGIN_HTML)
            if request.url.path == "/en/login" and request.method == "POST":
                logins += 1
                return httpx.Response(302, headers={"Location": "https://api.test/pl"})
            if request.url.path == "/pl/stream/posts":
                if logins == 0:
                    return httpx.Response(401, json={"message": "Unauthenticated."})
                return httpx.Response(200, json=[])
            raise AssertionError(f"unexpected {request.url.path}")

        client = make_web_client(handler)
        assert client.stream_posts(1) == []
        assert logins == 1

    def test_html_404_is_wrapped_as_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/en/login" and request.method == "GET":
                return httpx.Response(200, text=LOGIN_HTML)
            if request.url.path == "/en/login" and request.method == "POST":
                return httpx.Response(302, headers={"Location": "https://api.test/pl"})
            return httpx.Response(404, text="<!DOCTYPE html><html>not found</html>")

        client = make_web_client(handler)
        client._logged_in = True
        with pytest.raises(Exception, match="HTTP 404"):
            client.get("/pl/stream/whatever")
