# AGENTS.md — przewodnik dla agentów kodujących w tym repo

`protrainup-mcp` to **read-only** serwer MCP (stdio) opakowujący
nieudokumentowane API ProTrainUp (system zarządzania klubami sportowymi).
Python 3.10+, uv, SDK `mcp` 2.x.

## Komendy

```bash
uv sync                 # instalacja (.venv)
uv run pytest -q        # testy — MUSZĄ być offline i hermetyczne
uv run protrainup-mcp   # uruchomienie serwera MCP (stdio)
```

Weryfikacja na żywo (wymaga `.env` z loginem/hasłem — patrz zasady niżej):

```bash
uv run python -c "from protrainup_mcp.config import load_config; from protrainup_mcp.client import ProTrainUpClient; print(ProTrainUpClient(load_config()).whoami())"
```

## Twarde zasady

1. **Serwer pozostaje read-only.** Nie wystawiaj endpointów zapisu (POST/PUT/
   DELETE poza logowaniem i odczytowymi POST-ami typu lista zdarzeń).
   Endpointy zapisu (wysyłanie wiadomości itd.) wolno co najwyżej udokumentować.
2. **Credentiali nigdy nie czytaj, nie loguj, nie commituj.** Logują się z
   `PROTRAINUP_*` (env) lub `.env` (ładowany przez `config._env_file_overrides`
   — CWD, potem korzeń projektu; env ma pierwszeństwo). Nigdy nie otwieraj
   pliku `.env` użytkownika.
3. **Testy są offline i hermetyczne.** Zero sieci — tylko `httpx.MockTransport`
   (klienci przyjmują `transport=`). Fixture w `tests/test_config.py`
   monkeypatchuje `_env_file_candidates`, żeby prawdziwy `.env` nie włączał
   się do suity — nie cofaj tego. Nie dodawaj testów strzelających do
   protrainup.com; weryfikację live robi się ręcznie, poza suitą.
4. **SDK `mcp` 2.x**: importuj `MCPServer` z `mcp.server.mcpserver`
   (`FastMCP` już nie istnieje); floor w pyproject to `mcp>=2.0.0`.

## Wiedza domenowa (nieoczywista)

- API jest **nieudokumentowane** — zweryfikowane fakty żyją w docstringach
  modułów (`client.py`, `web.py`) i w README. Odkryjesz coś nowego → zaktualizuj
  je razem z kodem.
- **Konwencja nazewnictwa: liczba pojedyncza** (`/api/conversation`, nie
  `conversations`); relacje dołącza się parametrem `with` (lista po przecinku).
- **Dwa realm-y auth**: JWT (`/api/*`, pola `login`+`password`, nagłówek
  `Authorization: Bearer`) oraz sesja webowa (`/{lang}/*`, formularz z polem
  `username` + cookie sesji; POST-y dodatkowo wymagają CSRF z meta
  `csrf-token` pobieranego **po** zalogowaniu — token z formularza logowania
  jest po relogu nieaktualny; 419 → refresh tokenu, 401 → pełny re-login,
  zawsze dokładnie jedna próba).
- Każda subdomena klubowa to osobna instancja API — konto działa tylko na
  swojej (`PROTRAINUP_BASE_URL`).

## Layout

```
src/protrainup_mcp/
  config.py   # PROTRAINUP_* env + auto-ładowanie .env
  client.py   # realm API (JWT): auth, retry 401, znane endpointy
  web.py      # realm webowy (sesja+CSRF): stream, events/list, diary files
  server.py   # MCPServer + narzędzia ptu_* (sync, threadpool SDK → locki)
tests/        # offline, MockTransport, hermetyczne na .env
```

## Dodawanie narzędzia (checklist)

1. Metoda w `client.py` lub `web.py` (+ wiedza o endpoincie w docstringu).
2. `@mcp.tool()` w `server.py` — błędy zawsze jako JSON `{"error": ...}`
   (obsługiwane w `_run`), nigdy crash protokołu.
3. Dopisz nazwę do asercji pełnego zestawu narzędzi w `tests/test_server.py`
   i dodaj test offline z MockTransport.

Testy muszą przechodzić przed commitem: `uv run pytest -q`.
