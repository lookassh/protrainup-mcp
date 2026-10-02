# protrainup-mcp

An **MCP (Model Context Protocol) server** that exposes a ProTrainUp club
account (https://protrainup.com) to AI agents such as Hermes.

ProTrainUp does not publish an official API, but its mobile apps talk to an
undocumented API (Laravel + JWT). This server is a thin, deliberately
**read-only** wrapper over that API.

## Established API facts (reconnaissance 2026-10-01, verified live)

Every ProTrainUp club panel (subdomain, e.g. `your-club.protrainup.com`)
serves **its own copy of the same API** — an account only works on its own
club's subdomain, so set `PROTRAINUP_BASE_URL` to the address you log into
(default `https://api.protrainup.com`).

| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/login` | POST | login, fields `login` + `password`, returns a JWT |
| `/api/auth/me` | GET | current account |
| `/api/auth/refresh` | POST | refresh the JWT |
| `/api/auth/logout` | POST | invalidate the JWT |
| `/api/users/{id}` | GET | user profile (name, e-mail, avatar, `profile`; `created_by` in `me` points to the account creator) |
| `/api/calendar?from&to` | GET | club calendar; `from`/`to` (YYYY-MM-DD) **required**; events carry `type` (e.g. `training`), `oid`, `u_code`, location |
| `/api/tests[/{id}]` | GET | motoric test definitions (e.g. `10m_run`) with units |
| `/api/exercises` | GET | exercises (empty for some clubs) |
| `/api/conversation` | GET | conversation list with `participants` (`unread` counters), `users` (name/surname) |
| `/api/conversation/{id}?with=messages` | GET | conversation + full message history (`message`, `user_id`, `created_at`, `loggedIsSender`); `with` accepts a comma-separated list |
| `/api/conversation/{id}/message` | POST | **send a message** (field `message`) — intentionally NOT exposed |
| `/api/conversation` | POST | **new conversation** (fields `message` + `participants`) — intentionally NOT exposed |
| `/api/events`, `/api/users` | GET | routes exist but return 500 upstream (`Undefined method ::index`) |

Error format: `{"message": "...", "status_code": N}` (messages are Polish,
e.g. `"Pole login jest wymagane."`). Missing token: `401 "Token not provided"`.
Controllers live in the `App\Api\V1\Controllers\*` namespace.

Naming note: the API uses **singular** resource names (`conversation`,
`tests`, `exercises`) and nests resources the same way — when exploring
manually via `ptu_api_get`, try the singular form first.

### Club wall (web routes, panel session — not JWT)

Some data — notably the club activity stream — is not in the mobile `/api`
but in web panel routes protected by the **panel session** (cookie), not the
JWT. The server logs in in parallel with the login form (CSRF +
`username`/`password`) and keeps both sessions:

| Endpoint | Description |
|---|---|
| `GET /pl/stream/posts?stream=team&streamId={id}&page={n}` | team wall posts: author, html content, files, comments, likes, `pinInfo`, `policy` |
| `GET /pl/stream/scheduled-posts?stream=team&streamId={id}` | scheduled posts (often empty) |
| `POST /pl/events/list?f=all` + form `start`/`end` | calendar events (FullCalendar POST source) — richer than `/api/calendar`: `staff` (coach), `team_name`, `location_full`, a training preview `uri`; types `training`/`match`/`event` |
| `GET /pl/diary/files/open` | team disk file tree (folders + files with creator, size, date) |

Stream types: `team` (team id), `announcements` (club announcements scope
id), `user`/`group` (200, may be empty), `club`/`organization` (403 for a
parent-level account). Web routes answer JSON with
`Accept: application/json`, but their 404s are HTML pages.

POSTs need the **post-login CSRF token** (the `csrf-token` meta tag on panel
pages, sent as the `X-CSRF-TOKEN` header); it is fetched lazily and refreshed
on a 419 mismatch.

Players/payments-type paths do **not** exist in this API (~100 names
checked — 404). Panel data likely flows through other (web) routes; a
possible future step, e.g. browser-automation-based MCP tools.

The API is undocumented and **may change without notice**; handling of 401
with automatic re-login is built in.

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/) (or pip).

```bash
uv sync            # creates .venv and installs dependencies
uv run pytest      # tests (offline, no account needed)
```

## Configuration

Credentials (the same ones you use for the `app.protrainup.com` panel) can be
provided in two ways — real environment variables always take precedence:

1. **A `.env` file in the project directory** (auto-loaded, gitignored):
   ```bash
   cp .env.example .env   # then open .env and fill in login and password
   ```
2. Environment variables of the process (the `env` block in an MCP client
   config, `export` in a shell, or `setx` on Windows):

| Variable | Required | Description |
|---|---|---|
| `PROTRAINUP_LOGIN` | yes | ProTrainUp account login |
| `PROTRAINUP_PASSWORD` | yes | password |
| `PROTRAINUP_BASE_URL` | no | defaults to `https://api.protrainup.com` |
| `PROTRAINUP_TIMEOUT` | no | defaults to `30` seconds |

## MCP tools

| Tool | Description |
|---|---|
| `ptu_whoami` | verifies the credentials, returns the account (`/api/auth/me`) |
| `ptu_user` | user profile by id (`/api/users/{id}`) |
| `ptu_calendar` | club calendar for a date range (`/api/calendar`) |
| `ptu_tests` | motoric test definitions (`/api/tests`), optionally one by id |
| `ptu_exercises` | exercises (`/api/exercises`) |
| `ptu_conversations` | conversation list with unread counters (`/api/conversation`) |
| `ptu_messages` | full message history of one conversation (`/api/conversation/{id}?with=messages`) |
| `ptu_stream_posts` | team wall / club announcements (web route `/pl/stream/posts`, panel session) |
| `ptu_scheduled_posts` | posts scheduled on a stream (`/pl/stream/scheduled-posts`) |
| `ptu_events_list` | date-ranged events with coach/team/preview link (`POST /pl/events/list`) |
| `ptu_diary_files` | team disk file tree (`/pl/diary/files/open`) |
| `ptu_api_get` | safe passthrough: an authenticated **GET** to any API path (read-only) — for exploration |

## Connecting an MCP client (e.g. Hermes, Claude Desktop, Cursor)

The server speaks the **stdio** transport by default. Manual run:

```bash
uv run protrainup-mcp
```

Example MCP client configuration (Claude Desktop / most MCP clients format);
adjust the path to your clone:

```json
{
  "mcpServers": {
    "protrainup": {
      "command": "uv",
      "args": ["--directory", "C:\\\\path\\\\to\\\\protrainup-mcp", "run", "protrainup-mcp"],
      "env": {
        "PROTRAINUP_LOGIN": "your-login",
        "PROTRAINUP_PASSWORD": "your-password"
      }
    }
  }
}
```

If your agent does not support MCP natively, use any
function-calling→MCP bridge (e.g. the `mcp` Python SDK as a client) — all
tools return JSON as text, so they map 1:1 onto functions.

## Docker deployment (HTTP transport)

For agents running in containers (e.g. Hermes on Proxmox) the server can run
as an **HTTP sidecar** instead of a stdio subprocess:

```bash
docker compose up -d --build   # uses compose.yml and .env from the project dir
```

MCP endpoint: `http://protrainup-mcp:8000/mcp` (service name on the compose
network). Transport knobs:

| Variable | Default | Description |
|---|---|---|
| `PROTRAINUP_MCP_TRANSPORT` | `stdio` | `stdio` or `http` (alias: `streamable-http`) |
| `PROTRAINUP_MCP_HOST` | `127.0.0.1` (stdio) / `0.0.0.0` (http) | listen address |
| `PROTRAINUP_MCP_PORT` | `8000` | HTTP port |

> **Security note:** the HTTP endpoint has **no built-in authentication** —
> anyone who can reach the port uses your ProTrainUp account. Do not publish
> the port (`ports:`); keep it on the internal compose network or behind an
> authenticating reverse proxy.

If your agent (and its container) supports stdio servers, it is simpler to
install the package inside the agent's container:

```bash
pip install git+https://github.com/lookassh/protrainup-mcp.git
# then in the agent's MCP config: command "protrainup-mcp" + PROTRAINUP_* env
```

## Verification

```bash
# after setting PROTRAINUP_LOGIN/PROTRAINUP_PASSWORD
uv run python -c "from protrainup_mcp.config import load_config; from protrainup_mcp.client import ProTrainUpClient; print(ProTrainUpClient(load_config()).whoami())"
```

## Caveats

- The API is **private/undocumented** — you use it at your own risk and only
  with your own club account; it is worth asking ProTrainUp support about
  official access.
- The server performs **read-only** (GET) operations only. Write operations
  would have to be added deliberately later.
