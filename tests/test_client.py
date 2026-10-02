"""Offline client tests using httpx.MockTransport - no network, no credentials."""

from __future__ import annotations

import json

import httpx
import pytest

from protrainup_mcp.client import (
    ProTrainUpAPIError,
    ProTrainUpAuthError,
    ProTrainUpClient,
)
from protrainup_mcp.config import Config


def make_client(handler) -> ProTrainUpClient:
    config = Config(login="coach@example.com", password="secret", base_url="https://api.test")
    return ProTrainUpClient(config, transport=httpx.MockTransport(handler))


def ok(payload) -> httpx.Response:
    return httpx.Response(200, json=payload)


def api_error(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"message": message, "status_code": status})


class TestLogin:
    def test_sends_login_and_password_and_stores_token(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                seen["body"] = json.loads(request.content)
                return ok({"token": "jwt-abc"})
            raise AssertionError(f"unexpected path {request.url.path}")

        client = make_client(handler)
        assert client.login() == "jwt-abc"
        assert seen["body"] == {"login": "coach@example.com", "password": "secret"}

    def test_accepts_access_token_shape(self):
        client = make_client(lambda req: ok({"data": {"access_token": "xyz"}}))
        assert client.login() == "xyz"

    def test_missing_token_in_response_raises(self):
        client = make_client(lambda req: ok({"user": "coach"}))
        with pytest.raises(ProTrainUpAuthError, match="no token"):
            client.login()

    def test_wrong_credentials_raise_with_server_message(self):
        client = make_client(
            lambda req: api_error(401, "invalid_credentials")
        )
        with pytest.raises(ProTrainUpAuthError, match="invalid_credentials"):
            client.login()

    def test_validation_error_lists_field(self):
        client = make_client(
            lambda req: httpx.Response(
                422,
                json={
                    "message": "422 Unprocessable Content",
                    "errors": {"login": ["Pole login jest wymagane."]},
                },
            )
        )
        with pytest.raises(ProTrainUpAuthError, match="login: Pole login"):
            client.login()


class TestRequests:
    def test_get_auto_logs_in_and_sends_bearer(self):
        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/api/auth/login":
                return ok({"token": "jwt-1"})
            if request.headers.get("Authorization") == "Bearer jwt-1":
                return ok([{"id": 1, "name": "Trening"}])
            return api_error(401, "Token not provided")

        client = make_client(handler)
        assert client.tests() == [{"id": 1, "name": "Trening"}]
        assert requests[0].url.path == "/api/auth/login"
        assert requests[1].url.path == "/api/tests"

    def test_get_relogins_once_on_expired_token(self):
        login_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal login_count
            if request.url.path == "/api/auth/login":
                login_count += 1
                return ok({"token": f"jwt-{login_count}"})
            if request.headers.get("Authorization") != f"Bearer jwt-{login_count}":
                return api_error(401, "Token not provided")
            return ok({"ok": True})

        client = make_client(handler)
        client._token = "jwt-stale"
        assert client.exercises() == {"ok": True}
        assert login_count == 1

    def test_second_401_after_relogin_surfaces_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return ok({"token": "jwt-1"})
            return api_error(401, "Token not provided")

        client = make_client(handler)
        with pytest.raises(ProTrainUpAPIError, match="Token not provided"):
            client.get("/api/tests")

    def test_unauthenticated_500_message_triggers_relogin(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return ok({"token": "jwt-1"})
            if request.headers.get("Authorization") == "Bearer jwt-1":
                return ok({"id": 7, "login": "coach"})
            return httpx.Response(500, json={"message": "Unauthenticated.", "status_code": 500})

        client = make_client(handler)
        assert client.whoami()["id"] == 7

    def test_calendar_sends_required_from_to_params(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return ok({"token": "jwt-1"})
            if request.url.path == "/api/calendar":
                assert dict(request.url.params) == {"from": "2026-10-01", "to": "2026-10-31"}
                return ok([{"type": "training"}])
            raise AssertionError(f"unexpected path {request.url.path}")

        client = make_client(handler)
        assert client.calendar("2026-10-01", "2026-10-31") == [{"type": "training"}]

    def test_user_detail_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return ok({"token": "jwt-1"})
            if request.url.path == "/api/users/42":
                return ok({"id": 42})
            raise AssertionError(f"unexpected path {request.url.path}")

        client = make_client(handler)
        assert client.user(42) == {"id": 42}

    def test_conversation_list_and_messages(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return ok({"token": "jwt-1"})
            if request.url.path == "/api/conversation":
                return ok([{"id": 7, "participants": []}])
            if request.url.path == "/api/conversation/7":
                assert dict(request.url.params) == {"with": "messages"}
                return ok({"id": 7, "messages": [{"id": 1, "message": "hej"}]})
            raise AssertionError(f"unexpected path {request.url.path}")

        client = make_client(handler)
        assert client.conversations() == [{"id": 7, "participants": []}]
        assert client.conversation(7)["messages"] == [{"id": 1, "message": "hej"}]

    def test_conversation_without_messages_omits_param(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return ok({"token": "jwt-1"})
            if request.url.path == "/api/conversation/7":
                assert "with" not in request.url.params
                return ok({"id": 7})
            raise AssertionError(f"unexpected path {request.url.path}")

        client = make_client(handler)
        assert client.conversation(7, with_messages=False) == {"id": 7}

    def test_redirect_response_raises_instead_of_succeeding(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return ok({"token": "jwt-1"})
            return httpx.Response(302, headers={"Location": "https://api.test/en/login"})

        client = make_client(handler)
        with pytest.raises(ProTrainUpAPIError, match="unexpected redirect"):
            client.get("/api/tests")

    def test_non_json_body_is_wrapped(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/auth/login":
                return ok({"token": "jwt-1"})
            return httpx.Response(200, text="<html>legacy</html>")

        client = make_client(handler)
        assert client.get("/api/tests") == {"message": "<html>legacy</html>"}

    def test_missing_credentials_fail_fast(self):
        with pytest.raises(ProTrainUpAuthError, match="PROTRAINUP_LOGIN"):
            ProTrainUpClient(Config(login="", password=""))
