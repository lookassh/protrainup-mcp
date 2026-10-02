# protrainup-mcp

Serwer **MCP (Model Context Protocol)** wystawiający konto klubu w **ProTrainUp**
(https://protrainup.com) agentom AI, np. **Hermes**.

ProTrainUp nie publikuje oficjalnego API, ale jego aplikacje mobilne korzystają z
nieudokumentowanego API pod `https://api.protrainup.com` (Laravel + JWT). Ten
serwer jest cienką, **read-only** nakładką na to API.

## Ustalone fakty o API (rekonesans 2026-10-01, zweryfikowane na żywo)

Każdy panel klubowy ProTrainUp (subdomena, np. `twoj-klub.protrainup.com`)
wystawia **własną kopię tego samego API** — konto działa tylko na subdomenie
swojego klubu, dlatego ustaw `PROTRAINUP_BASE_URL` na adres, na którym się
logujesz (domyślnie `https://api.protrainup.com`).

| Endpoint | Metoda | Opis |
|---|---|---|
| `/api/auth/login` | POST | logowanie, pola `login` + `password`, zwraca JWT |
| `/api/auth/me` | GET | dane zalogowanego konta |
| `/api/auth/refresh` | POST | odświeżenie JWT |
| `/api/auth/logout` | POST | unieważnienie JWT |
| `/api/users/{id}` | GET | profil użytkownika (imię, e-mail, avatar, `profile`; `created_by` w `me` wskazuje konto założyciela) |
| `/api/calendar?from&to` | GET | kalendarz klubu; `from`/`to` (YYYY-MM-DD) **obowiązkowe**; zdarzenia z `type` (np. `training`), `oid`, `u_code`, lokalizacją |
| `/api/tests[/{id}]` | GET | definicje testów motorycznych (np. `10m_run`) z jednostkami |
| `/api/exercises` | GET | ćwiczenia (u części klubów pusta lista) |
| `/api/conversation` | GET | lista rozmów z `participants` (liczniki `unread`), `users` (imię/nazwisko) |
| `/api/conversation/{id}?with=messages` | GET | rozmowa + pełna historia wiadomości (`message`, `user_id`, `created_at`, `loggedIsSender`); `with` przyjmuje listę po przecinku |
| `/api/conversation/{id}/message` | POST | **wysyłanie** (pole `message`; wymagane, gdy brak załącznika) — celowo NIE wystawione serwerem |
| `/api/conversation` | POST | **nowa rozmowa** (pola `message` + `participants`) — celowo NIE wystawione |
| `/api/events`, `/api/users` | GET | route istnieją, ale po stronie serwera zwracają 500 (`Undefined method ::index`) |

Uwaga do nazewnictwa: API używa **liczby pojedynczej** (`conversation`, `tests`,
`exercises`) i tak samo mapuje zasoby zagnieżdżone — przy ręcznej eksploracji
przez `ptu_api_get` testuj najpierw formy pojedyncze.

### Ściana klubowa (web routes, sesja panelu — nie JWT)

Część danych idzie webowymi trasami `/{lang}/...` chronionymi **sesją panelu**
(cookie), nie tokenem JWT. Serwer loguje się równolegle formularzem (CSRF +
`username`/`password`) i trzyma obie sesje:

| Endpoint | Opis |
|---|---|
| `GET /pl/stream/posts?stream=team&streamId={id}&page={n}` | posty ze ściany drużyny: autor, treść HTML, pliki, komentarze, lajki, `pinInfo`, `policy` |
| `GET /pl/stream/scheduled-posts?stream=team&streamId={id}` | zaplanowane posty (często puste) |
| `POST /pl/events/list?f=all` + form `start`/`end` | zdarzenia kalendarza (źródło FullCalendar) — bogatsze niż `/api/calendar`: `staff` (trener), `team_name`, `location_full`, `uri` podglądu treningu; typy `training`/`match`/`event` |
| `GET /pl/diary/files/open` | drzewo plików „Dysk zespołu" (foldery + pliki z twórcą, rozmiarem, datą) |

POST-y wymagają **CSRF po zalogowaniu** (meta `csrf-token` ze strony panelu, nagłówek `X-CSRF-TOKEN`) — klient pobiera go leniwie i odświeża przy 419.

Typy strumienia: `team` (id drużyny), `announcements` (id zakresu ogłoszeń
klubu), `user`/`group` (200, mogą być puste), `club`/`organization`
(403 dla konta rodzica). Web routes zwracają JSON po
`Accept: application/json`, ale ich 404 to strony HTML.

Format błędów: `{"message": "...", "status_code": N}` (po polsku). Brak tokenu:
`401 "Token not provided"`. Kontrolery: namespace `App\Api\V1\Controllers\*`.

Ścieżki typu zawodnicy/płatności **nie istnieją** w tym API
(sprawdzone ~100 nazw — 404). Prawdopodobnie dane panelu webowego idą innymi
ścieżkami (webowe trasy Laravela, nie `/api/*`); do zbadania później, np.
przez narzędzia MCP oparte o przeglądarkę.

API jest nieudokumentowane i **może się zmienić bez ostrzeżenia**; obsługa 401
z automatycznym ponownym logowaniem jest wbudowana.

## Instalacja

Wymaga Pythona 3.10+ i [uv](https://docs.astral.sh/uv/) (lub pip).

```bash
uv sync            # tworzy .venv i instaluje zależności
uv run pytest      # testy (offline, nie potrzebują konta)
```

## Konfiguracja

Dane logowania (te same, co do panelu `app.protrainup.com`) można podać na dwa
sposoby — zmienne środowiskowe mają zawsze pierwszeństwo:

1. **Plik `.env` w katalogu projektu** (wczytywany automatycznie, gitignore'owany):
   ```bash
   cp .env.example .env   # potem otwórz .env i wpisz login oraz hasło
   ```
2. Zmienne środowiskowe procesu (blok `env` w konfiguracji klienta MCP, `export`
   w powłoce albo `setx` w Windows):

| Zmienna | Obowiązkowa | Opis |
|---|---|---|
| `PROTRAINUP_LOGIN` | tak | login do konta ProTrainUp |
| `PROTRAINUP_PASSWORD` | tak | hasło |
| `PROTRAINUP_BASE_URL` | nie | domyślnie `https://api.protrainup.com` |
| `PROTRAINUP_TIMEOUT` | nie | domyślnie `30` sekund |

## Narzędzia MCP

| Narzędzie | Opis |
|---|---|
| `ptu_whoami` | weryfikuje dane logowania, zwraca konto (`/api/auth/me`) |
| `ptu_user` | profil użytkownika po id (`/api/users/{id}`) |
| `ptu_calendar` | kalendarz klubu w zakresie dat `from`–`to` (`/api/calendar`) |
| `ptu_tests` | definicje testów motorycznych (`/api/tests`), opcjonalnie jeden po id |
| `ptu_exercises` | ćwiczenia (`/api/exercises`) |
| `ptu_conversations` | lista rozmów z licznikami nieprzeczytanych (`/api/conversation`) |
| `ptu_messages` | pełna historia wiadomości jednej rozmowy (`/api/conversation/{id}?with=messages`) |
| `ptu_stream_posts` | ściana drużyny (web route `/pl/stream/posts`, sesja panelu) |
| `ptu_scheduled_posts` | zaplanowane posty na ścianie (`/pl/stream/scheduled-posts`) |
| `ptu_events_list` | zdarzenia z datami + trener/drużyna/link podglądu (`POST /pl/events/list`) |
| `ptu_diary_files` | drzewo plików „Dysk zespołu" (`/pl/diary/files/open`) |
| `ptu_api_get` | bezpieczny passthrough: uwierzytelniony **GET** po dowolnej ścieżce API (tylko odczyt) — do eksploracji |

## Podłączenie klienta MCP (np. Hermes, Claude Desktop, Cursor)

Serwer pracuje na transporcie **stdio**. Uruchomienie ręczne:

```bash
uv run protrainup-mcp
```

Przykładowa konfiguracja klienta MCP (format zgodny z Claude Desktop / większością
klientów MCP); podmień ścieżkę na lokalizację klonu repo:

```json
{
  "mcpServers": {
    "protrainup": {
      "command": "uv",
      "args": ["--directory", "C:\\\\path\\\\to\\\\protrainup-mcp", "run", "protrainup-mcp"],
      "env": {
        "PROTRAINUP_LOGIN": "twoj-login",
        "PROTRAINUP_PASSWORD": "twoje-haslo"
      }
    }
  }
}
```

Jeśli Twój agent nie obsługuje MCP natywnie, użyj dowolnego mostu
function-calling→MCP (np. `mcp` Python SDK jako klient) — wszystkie narzędzia
zwracają JSON w postaci tekstu, więc mapują się 1:1 na funkcje.

## Uruchomienie w Dockerze (transport HTTP)

Dla agentów działających w kontenerach (np. Hermes na Proxmoxie) serwer można
postawić jako **sidecar HTTP** zamiast procesu stdio:

```bash
docker compose up -d --build   # używa compose.yml i .env z katalogu projektu
```

Endpoint MCP: `http://protrainup-mcp:8000/mcp` (nazwa serwisu w sieci compose).
Sterowanie transportem zmiennymi:

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `PROTRAINUP_MCP_TRANSPORT` | `stdio` | `stdio` lub `http` (alias: `streamable-http`) |
| `PROTRAINUP_MCP_HOST` | `127.0.0.1` (stdio) / `0.0.0.0` (http) | adres nasłuchu |
| `PROTRAINUP_MCP_PORT` | `8000` | port HTTP |

> **Uwaga bezpieczeństwa:** endpoint HTTP **nie ma własnej autoryzacji** —
> każdy, kto dosięgnie portu, używa Twojego konta ProTrainUp. Nie publikuj
> portu na zewnątrz (`ports:`); trzymaj go w sieci wewnętrznej compose lub
> za reverse proxy z autoryzacją.

Jeśli agent (i jego kontener) obsługuje serwery stdio, prościej jest
zainstalować pakiet wewnątrz kontenera agenta:

```bash
pip install git+https://github.com/lookassh/protrainup-mcp.git
# a w konfiguracji MCP agenta: command "protrainup-mcp" + env PROTRAINUP_*
```

## Weryfikacja

```bash
# po ustawieniu PROTRAINUP_LOGIN/PROTRAINUP_PASSWORD
uv run python -c "from protrainup_mcp.config import load_config; from protrainup_mcp.client import ProTrainUpClient; print(ProTrainUpClient(load_config()).whoami())"
```

## Zastrzeżenia

- API jest **prywatne/nieudokumentowane** — korzystasz na własną odpowiedzialność
  i wyłącznie z własnym kontem klubu; warto zapytać wsparcie ProTrainUp o oficjalny dostęp.
- Serwer wykonuje wyłącznie operacje **odczytu** (GET). Ewentualne operacje zapisu
  trzeba świadomie dodać później.
