"""HTTP client for the ProTrainUp mobile API.

The API is undocumented (it backs the ProTrainUp mobile apps); the surface
below was mapped live against a club panel subdomain (every club subdomain
serves the same API):

- POST /api/auth/login      {login, password} -> JWT (tymon/jwt-auth style)
- POST /api/auth/refresh / /api/auth/logout   -> JWT lifecycle
- GET  /api/auth/me                            -> current account
- GET  /api/users/{id}                         -> user profile (200)
- GET  /api/calendar?from=YYYY-MM-DD&to=...    -> club calendar events
- GET  /api/tests[/{id}]                       -> motoric test definitions
- GET  /api/exercises                          -> exercises (may be empty)
- GET  /api/conversation                       -> conversations (participants, unread)
- GET  /api/conversation/{id}?with=messages    -> conversation with full messages
- GET  /api/events                             -> broken upstream (500)

Write endpoints mapped but intentionally NOT used by this read-only client:
- POST /api/conversation/{id}/message   {message}          -> send message
- POST /api/conversation                {message, participants} -> new conversation

Note: GET /api/users and /api/events exist as routes but their index methods
are undefined upstream (HTTP 500 "Undefined method ... ::index").

Error format: {"message": "...", "status_code": N} with HTTP status to match.
"""

from __future__ import annotations

import threading
from typing import Any, Mapping

import httpx

from .config import Config

LOGIN_PATH = "/api/auth/login"
ME_PATH = "/api/auth/me"
USERS_PATH = "/api/users"
CALENDAR_PATH = "/api/calendar"
TESTS_PATH = "/api/tests"
EXERCISES_PATH = "/api/exercises"
CONVERSATIONS_PATH = "/api/conversation"

# tymon/jwt-auth returns {"token": "..."} by default; other shapes kept as fallbacks.
_TOKEN_KEYS = ("token", "access_token", "jwt", "api_token")


class ProTrainUpError(Exception):
    """Base error for ProTrainUp client failures."""


class ProTrainUpAuthError(ProTrainUpError):
    """Raised when login fails or the API rejects the token."""


class ProTrainUpAPIError(ProTrainUpError):
    """Raised for non-2xx API responses that are not auth problems."""

    def __init__(self, status_code: int, message: str, body: Any = None):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


def _extract_token(payload: Any) -> str | None:
    if isinstance(payload, Mapping):
        for key in _TOKEN_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        nested = payload.get("data")
        if nested is not payload:
            return _extract_token(nested)
    return None


def error_message(status_code: int, payload: Any) -> str:
    """Best-effort human-readable message from a ProTrainUp error payload."""
    if isinstance(payload, Mapping):
        if isinstance(payload.get("errors"), Mapping) and payload["errors"]:
            first_field = next(iter(payload["errors"]))
            details = payload["errors"][first_field]
            if isinstance(details, list) and details:
                return f"{first_field}: {details[0]}"
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"unexpected response (HTTP {status_code})"


class ProTrainUpClient:
    """Thin, read-oriented client with automatic JWT login and re-login."""

    def __init__(
        self,
        config: Config,
        transport: httpx.BaseTransport | None = None,
    ):
        if not config.has_credentials:
            raise ProTrainUpAuthError(
                "ProTrainUp credentials are missing: set PROTRAINUP_LOGIN and "
                "PROTRAINUP_PASSWORD environment variables."
            )
        self._config = config
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={"Accept": "application/json"},
            transport=transport,
        )
        self._token: str | None = None
        # MCP servers dispatch sync tools from a threadpool; guards the
        # lazy login and 401 re-login from running twice in parallel.
        self._lock = threading.Lock()

    # -- auth ------------------------------------------------------------

    def login(self) -> str:
        response = self._http.post(
            LOGIN_PATH,
            json={"login": self._config.login, "password": self._config.password},
        )
        payload = self._parse(response)
        if response.status_code in (401, 403, 422):
            raise ProTrainUpAuthError(
                f"Login failed: {error_message(response.status_code, payload)}"
            )
        if response.status_code >= 400:
            raise ProTrainUpAPIError(
                response.status_code,
                error_message(response.status_code, payload),
                payload,
            )
        token = _extract_token(payload)
        if token is None:
            raise ProTrainUpAuthError(
                f"Login succeeded but no token found in response: {payload!r}"
            )
        self._token = token
        return token

    # -- requests ----------------------------------------------------------

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def whoami(self) -> Any:
        return self.get(ME_PATH)

    def user(self, user_id: Any) -> Any:
        return self.get(f"{USERS_PATH}/{user_id}")

    def calendar(self, from_date: str, to_date: str, extra_params: Mapping[str, Any] | None = None) -> Any:
        """Club calendar; `from`/`to` (YYYY-MM-DD) are required by the API."""
        params = {"from": from_date, "to": to_date}
        if extra_params:
            params.update(extra_params)
        return self.get(CALENDAR_PATH, params)

    def tests(self, test_id: Any = None) -> Any:
        path = TESTS_PATH if test_id is None else f"{TESTS_PATH}/{test_id}"
        return self.get(path)

    def exercises(self, params: Mapping[str, Any] | None = None) -> Any:
        return self.get(EXERCISES_PATH, params)

    def conversations(self) -> Any:
        """All conversations of the account, with participants and unread counts."""
        return self.get(CONVERSATIONS_PATH)

    def conversation(self, conversation_id: Any, with_messages: bool = True) -> Any:
        """One conversation; `with=messages` attaches full message history."""
        params = {"with": "messages"} if with_messages else None
        return self.get(f"{CONVERSATIONS_PATH}/{conversation_id}", params)

    # -- internals -----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        if self._token is None:
            with self._lock:
                if self._token is None:
                    self.login()
        assert self._token is not None
        response = self._http.request(
            method,
            path,
            params=params,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if response.status_code == 401 and retry_auth:
            # Token rejected (expired/revoked) - re-login once under the
            # lock and retry.
            with self._lock:
                self._token = None
                self.login()
            return self._request(method, path, params=params, retry_auth=False)

        if response.has_redirect_location:
            # JSON endpoints never redirect on success; a 3xx here means
            # the route changed or auth bounced us somewhere unexpected.
            raise ProTrainUpAPIError(
                response.status_code,
                f"unexpected redirect to {response.headers.get('location', '?')}",
            )

        payload = self._parse(response)
        if response.status_code >= 400:
            message = error_message(response.status_code, payload)
            # /api/auth/me reports a missing token as HTTP 500 "Unauthenticated."
            if message == "Unauthenticated." and retry_auth:
                with self._lock:
                    self._token = None
                    self.login()
                return self._request(method, path, params=params, retry_auth=False)
            raise ProTrainUpAPIError(response.status_code, message, payload)
        return payload

    @staticmethod
    def _parse(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"message": response.text[:2000]}
