"""Client for ProTrainUp web-panel routes (session auth, /{lang}/... paths).

Some data - notably the club activity stream - is not in the mobile /api but
in web panel routes that require the Laravel web session (cookie), not the
JWT. Mapped live (2026-10-01) on a club panel subdomain:

- POST /en/login                    form: _token, username, password, remember
- GET  /{lang}/stream/posts?stream=team&streamId={id}&page={n}   -> JSON posts
- GET  /{lang}/stream/scheduled-posts?stream=team&streamId={id}  -> JSON
- POST /{lang}/events/list?f=all    form: start, end (FullCalendar event source)
                                     -> richer events than /api/calendar
                                        (staff, team_name, location_full, uri)
- GET  /{lang}/diary/files/open     -> team disk file tree (folders + files)

Posts embed user, html content, files, comments, likes, pinInfo and policy.
Stream types: "team" (works), "announcements" (club-wide), "user"/"group"
(200, may be empty), "club"/"organization" (403 for a parent-level account).

POSTs need the post-login CSRF token (meta csrf-token on panel pages) via the
X-CSRF-TOKEN header; it is fetched lazily and refreshed on a 419 mismatch.

Web routes answer JSON when called with Accept: application/json; their 404s
are HTML pages.
"""

from __future__ import annotations

import re
import threading
from typing import Any, Mapping

import httpx

from .client import ProTrainUpAPIError, ProTrainUpAuthError, error_message
from .config import Config

_TOKEN_RE = re.compile(r'name="_token" value="([^"]+)"')
_CSRF_META_RE = re.compile(r'<meta name="csrf-token" content="([^"]+)"')


class WebSessionClient:
    """Cookie-session client for web panel routes, with auto re-login."""

    def __init__(
        self,
        config: Config,
        transport: httpx.BaseTransport | None = None,
        lang: str = "pl",
    ):
        if not config.has_credentials:
            raise ProTrainUpAuthError(
                "ProTrainUp credentials are missing: set PROTRAINUP_LOGIN and "
                "PROTRAINUP_PASSWORD environment variables."
            )
        self._config = config
        self._lang = lang
        self._logged_in = False
        self._csrf: str | None = None
        # MCP servers dispatch sync tools from a threadpool; guards login
        # and the CSRF cache from racing parallel tool calls.
        self._lock = threading.Lock()
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            follow_redirects=False,
            headers={
                "User-Agent": "Mozilla/5.0 (protrainup-mcp)",
                "Accept": "application/json",
            },
            transport=transport,
        )

    # -- auth ------------------------------------------------------------

    def login(self) -> None:
        """CSRF + form login; the session cookie stays in the client jar."""
        page = self._http.get("/en/login")
        match = _TOKEN_RE.search(page.text)
        if match is None:
            raise ProTrainUpAuthError("Web login failed: no CSRF token on the login page.")
        response = self._http.post(
            "/en/login",
            data={
                "_token": match.group(1),
                "username": self._config.login,
                "password": self._config.password,
                "remember": "1",
            },
        )
        location = response.headers.get("location", "")
        if response.status_code >= 400:
            raise ProTrainUpAuthError(
                f"Web login failed: {error_message(response.status_code, self._parse(response))}"
            )
        if "/login" in location:
            # bounced back to the login form -> credentials rejected
            raise ProTrainUpAuthError("Web login failed: redirected back to the login form.")
        if response.status_code == 200 and 'name="password"' in response.text:
            # some Laravel flows re-render the login form with errors (200)
            # instead of redirecting back
            raise ProTrainUpAuthError("Web login failed: login form re-rendered.")
        self._logged_in = True
        self._csrf = None  # session was regenerated on login

    def _get_csrf(self, refresh: bool = False) -> str:
        """Post-login CSRF token from the panel page (meta csrf-token)."""
        if self._csrf is None or refresh:
            with self._lock:
                if self._csrf is None or refresh:
                    panel = self._http.get(f"/{self._lang}")
                    match = _CSRF_META_RE.search(panel.text) or _TOKEN_RE.search(panel.text)
                    if match is None:
                        raise ProTrainUpAuthError("No CSRF token found on the panel page.")
                    self._csrf = match.group(1)
        return self._csrf

    # -- stream ----------------------------------------------------------

    def stream_posts(
        self, stream_id: Any, stream: str = "team", page: int = 0
    ) -> Any:
        return self.get(
            f"/{self._lang}/stream/posts",
            params={"stream": stream, "streamId": stream_id, "page": page},
        )

    def scheduled_posts(self, stream_id: Any, stream: str = "team") -> Any:
        return self.get(
            f"/{self._lang}/stream/scheduled-posts",
            params={"stream": stream, "streamId": stream_id},
        )

    def events_list(self, from_date: str, to_date: str, event_filter: str = "all") -> Any:
        """Calendar events (FullCalendar POST source): richer than /api/calendar -
        includes staff, team_name, location_full and a preview uri per event.
        """
        return self._post(
            f"/{self._lang}/events/list",
            params={"f": event_filter},
            data={"start": from_date, "end": to_date},
        )

    def diary_files(self) -> Any:
        """Team disk file tree (folders with nested files: name, creator, size, date)."""
        return self.get(f"/{self._lang}/diary/files/open")

    # -- requests ----------------------------------------------------------

    def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        return self._request("GET", path, params)

    def _post(
        self,
        path: str,
        data: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        if not self._logged_in:
            with self._lock:
                if not self._logged_in:
                    self.login()
        response = self._http.post(
            path, data=data, params=params,
            headers={"X-CSRF-TOKEN": self._get_csrf(), "X-Requested-With": "XMLHttpRequest"},
        )
        if response.status_code == 419:
            # CSRF token went stale - refresh once and retry.
            response = self._http.post(
                path, data=data, params=params,
                headers={"X-CSRF-TOKEN": self._get_csrf(refresh=True),
                         "X-Requested-With": "XMLHttpRequest"},
            )
        if response.status_code == 401:
            # Session expired - full re-login and one more try.
            with self._lock:
                self._logged_in = False
                self._csrf = None
                self.login()
            response = self._http.post(
                path, data=data, params=params,
                headers={"X-CSRF-TOKEN": self._get_csrf(refresh=True),
                         "X-Requested-With": "XMLHttpRequest"},
            )
        payload = self._parse(response)
        if response.status_code >= 400:
            raise ProTrainUpAPIError(
                response.status_code,
                error_message(response.status_code, payload),
                payload,
            )
        return payload

    def _request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        if not self._logged_in:
            with self._lock:
                if not self._logged_in:
                    self.login()
        response = self._http.request(method, path, params=params)
        if response.status_code == 401 and retry_auth:
            # Session expired - log in again and retry once.
            with self._lock:
                self._logged_in = False
                self._csrf = None
                self.login()
            return self._request(method, path, params, retry_auth=False)
        if response.has_redirect_location:
            # JSON routes answer 200; a 3xx here means the session bounced
            # us to an HTML page - surface it instead of returning markup.
            raise ProTrainUpAPIError(
                response.status_code,
                f"unexpected redirect to {response.headers.get('location', '?')}",
            )

        payload = self._parse(response)
        if response.status_code >= 400:
            raise ProTrainUpAPIError(
                response.status_code,
                error_message(response.status_code, payload),
                payload,
            )
        return payload

    @staticmethod
    def _parse(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"message": response.text[:2000]}
