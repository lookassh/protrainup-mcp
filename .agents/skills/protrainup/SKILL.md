---
name: protrainup
description: Work with a ProTrainUp sports club account through the protrainup-mcp MCP server (ptu_* tools). Use whenever the user asks about their club - trainings, matches, schedule, messages from coaches, absences, club announcements, team files, or motoric tests - even if they don't name ProTrainUp explicitly. Also use for any question about ptu_* tools or their errors.
---

# ProTrainUp club data via protrainup-mcp

You are answering questions about a sports club in **ProTrainUp** using the
read-only `protrainup-mcp` MCP server. Club data is in Polish (team names,
locations, messages); answer in the user's language, quote Polish content
verbatim only when it matters.

## Prerequisite

The `ptu_*` tools must be available (MCP server connected via stdio or
`http://…/mcp`). If they are missing, tell the user to connect
`protrainup-mcp` first (https://github.com/lookassh/protrainup-mcp) and stop.

Everything is **read-only** - you cannot send messages or edit anything, by
design. If asked to write, say so instead of trying.

## The tools, by what the user wants

| User asks about | Call | Notes |
|---|---|---|
| trainings/matches in a period | `ptu_events_list(from_date, to_date)` | richest: coach (`staff`), `team_name`, `location_full`, type `training`/`match`/`event` |
| schedule (fallback) | `ptu_calendar(from_date, to_date)` | same range API-side; `ptu_events_list` is strictly richer - prefer it |
| messages, "anything new from the coach?" | `ptu_conversations()` → `ptu_messages(conversation_id)` | always this order: list first (it has the ids and `unread` counts), then history |
| who am I / my id | `ptu_whoami()` | also gives `created_by` (the account creator, e.g. the club admin) |
| a person mentioned in data | `ptu_user(user_id)` | ids come from message authors, conversation users, `created_by` |
| club/team wall, announcements | `ptu_stream_posts(stream_id, stream)` | `stream="team"` (team wall) or `stream="announcements"` (club-wide); ids are club-specific - take them from the user or earlier conversation, they are NOT discoverable via the API |
| scheduled (future) posts | `ptu_scheduled_posts(stream_id, stream)` | often empty - that is normal |
| files: schedules, call-ups, photos | `ptu_diary_files()` | returns a tree: folders with nested `data` arrays; file names often contain the actual message |
| fitness tests (10m run etc.) | `ptu_tests()` | definitions with units; results are not exposed by the API |
| anything else / exploration | `ptu_api_get(path)` | authenticated GET passthrough; try singular resource names (`/api/conversation`, not `conversations`) |

## Workflows that work

**"What's this week look like?"** → `ptu_events_list` for Mon–Sun
(YYYY-MM-DD). Group by day; mention coach and location for trainings, and
highlight matches.

**"Any unread messages?"** → `ptu_whoami` (get your id) → `ptu_conversations`
→ for each conversation sum `unread` from `participants` entries where
`user_id` matches you → if > 0, `ptu_messages(conversation_id)` and summarize.
Absence notifications ("Zawodnik … nie będzie obecny…") arrive as regular
messages - surface them.

**"What's new at the club?"** → both `ptu_stream_posts` calls (team +
announcements). Posts embed `comments`, `likes`, `files`, and `html` content -
strip tags when summarizing, don't dump raw HTML.

## Gotchas (verified against the live API)

- Dates are `YYYY-MM-DD`; event times are local club time
  (`"2026-10-02 17:45:00"`).
- `ptu_calendar`/`ptu_events_list` REQUIRE both dates - the API rejects
  half-open ranges with 422.
- Error format is `{"error": "…"}` JSON. Auth errors are retried
  automatically once; if they persist, credentials are wrong/expired - say
  that plainly instead of retrying in a loop.
- The upstream API is undocumented and sometimes broken (e.g. `/api/events`
  returns 500 forever). If a tool errors consistently, it's the API, not you.
- Stream ids live in two different id spaces (`team` vs `announcements`) -
  never reuse an id across stream types.

## Privacy

Data includes minors (players) and their parents. Summarize; don't enumerate
rosters or dump raw personal data unless the user explicitly asks for a
specific item.
