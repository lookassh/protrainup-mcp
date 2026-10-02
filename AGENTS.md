# AGENTS.md — a guide for coding agents working in this repo

`protrainup-mcp` is a **read-only** MCP (stdio/HTTP) server wrapping the
undocumented ProTrainUp API (a sports club management system).
Python 3.10+, uv, `mcp` SDK 2.x.

## Commands

```bash
uv sync                 # install (.venv)
uv run pytest -q        # tests — MUST be offline and hermetic
uv run protrainup-mcp   # MCP server, stdio (default)
PROTRAINUP_MCP_TRANSPORT=http uv run protrainup-mcp   # HTTP variant (sidecar)
```

Live verification (needs `.env` with login/password — see rules below):

```bash
uv run python -c "from protrainup_mcp.config import load_config; from protrainup_mcp.client import ProTrainUpClient; print(ProTrainUpClient(load_config()).whoami())"
```

## Hard rules

1. **The server stays read-only.** Do not expose write endpoints
   (POST/PUT/DELETE beyond login and read-style POSTs such as the events
   list). Write endpoints (sending messages etc.) may at most be documented.
2. **Never read, log, or commit credentials.** They come from `PROTRAINUP_*`
   (env) or `.env` (loaded by `config._env_file_overrides` — CWD first, then
   project root; env takes precedence; quotes are stripped only as a matched
   pair). Never open the user's `.env` file.
3. **Tests are offline and hermetic.** Zero network — `httpx.MockTransport`
   only (the clients accept `transport=`). The fixture in `tests/test_config.py`
   monkeypatches `_env_file_candidates` so the developer's real `.env` never
   enters the suite — do not undo that. Never add tests that hit
   protrainup.com; live verification is done manually, outside the suite.
4. **`mcp` SDK 2.x**: import `MCPServer` from `mcp.server.mcpserver`
   (`FastMCP` no longer exists); the pyproject floor is `mcp>=2.0.0`.

## Domain knowledge (the non-obvious parts)

- The API is **undocumented** — verified facts live in the module docstrings
  (`client.py`, `web.py`) and in the README. Discover something new → update
  them together with the code.
- **Naming convention: singular** (`/api/conversation`, not `conversations`);
  relations are attached with the `with` query param (comma-separated list).
- **Two auth realms**: JWT (`/api/*`, fields `login`+`password`,
  `Authorization: Bearer` header) and the web session (`/{lang}/*`, a form
  with the `username` field + a session cookie; POSTs additionally need the
  CSRF token from the `csrf-token` meta fetched **after** login — the token
  from the login form is stale after a re-login; 419 → refresh the token,
  401 → full re-login, always exactly one attempt).
- Every club subdomain is a separate API instance — an account only works on
  its own (`PROTRAINUP_BASE_URL`).

## Layout

```
src/protrainup_mcp/
  config.py   # PROTRAINUP_* env + .env auto-loading + transport config
  client.py   # API realm (JWT): auth, 401 retry, known endpoints
  web.py      # web realm (session+CSRF): stream, events/list, diary files
  server.py   # MCPServer + ptu_* tools (sync; SDK threadpool → locks)
tests/        # offline, MockTransport, hermetic against .env
```

## Adding a tool (checklist)

1. A method in `client.py` or `web.py` (+ endpoint knowledge in the docstring).
2. `@mcp.tool()` in `server.py` — errors always as JSON `{"error": ...}`
   (handled in `_run`), never a protocol crash.
3. Add the name to the full tool-set assertion in `tests/test_server.py`
   and an offline MockTransport test.

Tests must pass before committing: `uv run pytest -q`.
