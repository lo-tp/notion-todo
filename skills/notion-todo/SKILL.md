---
name: notion-todo
description: Manage Notion cards (tasks, time tracking) via scripts/notion_cards.py and the local SQLite mirror. Use when the user asks to sync, create/update/delete a task, log or summarize time, asks about their tasks/records/projects, or wants a report or overview.
---

# Notion Card Management

Mutations go through the `notion_cards` CLI (auto-syncs the mirror after every mutation). Reads go through the local SQLite mirror — for SQL recipes, table schemas, and report formats, read [`queries.md`](queries.md).

## Running scripts

```bash
bash <root>/scripts/run.sh <script-name> [args...]
```

`<root>` is the project root — the directory containing `pyproject.toml` and `.venv`. Walk up from the current working directory to find it; do not assume cwd is the root. The runner uses `<root>/.venv/bin/python`, sources the nearest `.env`, and maps `<script-name>` to `<root>/scripts/<script-name>.py`. Never hard-code an interpreter path.

## Session start

Preload card context so the user's loose references can be fuzzy-matched:

```bash
bash <root>/scripts/run.sh notion_cards recent
bash <root>/scripts/run.sh notion_cards frequent
```

Re-run mid-session for a fresher set.

## CLI

```bash
# Create (only the fields you pass are set)
run.sh notion_cards create <name> [--status S] [--due YYYY-MM-DD] [--project NAME] [--tags a,b] [--priority 5] [--description TEXT]

# Modify (empty value clears a field; tags/project replaced wholesale)
run.sh notion_cards modify <task> [--name NEW] [same flags as create]

# Delete (Notion archive — no hard delete via API)
run.sh notion_cards delete <task>

# Time tracking
run.sh notion_cards start <task> [description]   # stops any open tracker first; description (optional) is stored on the time tracking record
run.sh notion_cards end            # stops every open tracker; idempotent

# Comments (Notion-only, not mirrored — no sync needed)
run.sh notion_cards comment <card> read
run.sh notion_cards comment <card> create "text"
run.sh notion_cards comment <card> update "new text" [comment-id]
run.sh notion_cards comment <card> delete [comment-id]

# Page content (Notion-only, not mirrored — no sync needed)
run.sh notion_cards page <card> read
run.sh notion_cards page <card> create "text"     # appends a paragraph
run.sh notion_cards page <card> update "new text" [block-id]
run.sh notion_cards page <card> delete [block-id]

# Sync (incremental by default; --full also soft-deletes records gone from Notion)
run.sh notion_cards sync [--full]

# Context preload
run.sh notion_cards recent [N]           # recent tasks with ids (N defaults to RECENT_CARDS_LIMIT, then 20)
run.sh notion_cards frequent [--limit N] # frequent tasks + projects, printed as "  <id>  <name>" (N defaults to 15)
```

- Cards resolve by UUID → exact name → unique substring; ambiguous matches are rejected.
- `--project` links an existing project (name, unique substring, or UUID); it never creates one.
- `update`/`delete` without an id act on the card's latest comment / last block. Page `update` replaces text (text blocks only: paragraph, headings, list items, to-do, callout, quote).
- Default to incremental sync; `--full` only when the user explicitly asks.
- On schema mismatch, do NOT sync — stop and report which fields are new or missing (then update `sync/schema.sql` and `sync/sync.py`). On HTTP 429, wait and retry.
- **Single running tracker invariant:** at most one open tracker. `start` enforces it.

## Ad-hoc snippets

Only for mirror queries the `queries.md` recipes don't cover, or one-off Notion API calls the CLI doesn't have (e.g. logging a past time entry). If a CLI subcommand covers the request, use it.

Write the snippet to `<root>/scripts/_adhoc.py` from the template, run `bash <root>/scripts/run.sh _adhoc`, then delete the file. This runs it in the project venv with `.env` loaded.

```python
import os, sqlite3, sys
from pathlib import Path

# ── SQLite mirror ──
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sync"))
import sync
conn = sync.connect(sync.db_path(os.environ))  # FK pragma on; honors MIRROR_PATH override
conn.row_factory = sqlite3.Row

# ── Notion client (uncomment only if the script calls the API) ──
# from notion_client import Client
# notion = Client(auth=os.environ["NOTION_TOKEN"])
# TIME_TRACKING_DB = os.environ["NOTION_DB_TIME_TRACKING"]

# ── Your code ──
for row in conn.execute("SELECT name, status FROM tasks WHERE deleted_at IS NULL").fetchall():
    print(row["name"], "|", row["status"])
```

- All Notion calls use the `notion-client` library, one client per run; reference for API issues: https://developers.notion.com/reference/intro
- Never modify the mirror directly — if the snippet mutates Notion, finish with `run.sh notion_cards sync`.
- Timestamps are ISO-8601 strings; write times with `datetime.now().astimezone().isoformat()`; display local time, never UTC.
- `tags` is a JSON list of strings (e.g. `["a", "b"]`); filter `deleted_at IS NULL`.

## Log a past time entry

No CLI subcommand — one-off API call. Create the page (start/end in the user's local timezone, e.g. `2026-09-22T09:00:00+08:00`), then `run.sh notion_cards sync`:

```python
notion.pages.create(parent={"database_id": TIME_TRACKING_DB}, properties={
    "Name": {"title": [{"text": {"content": name or "Time entry"}}]},
    "Start Time": {"date": {"start": start_time}},
    "End Time": {"date": {"start": end_time}},
    "Status": {"select": {"name": "Stopped"}},
    "Tasks": {"relation": [{"id": task_id}]},
})
```

Patterns: "Log 30 minutes on X" → start=now-30min, end=now. "Log 1 hour this morning" → 9am–10am.

## Rules

- Never start a time tracker on a card in a finished status (`Done`/`Finished`). If the user asks for it, confirm first.
- Always confirm before creating a Notion entity (task, project, record, comment, page block) — the only exception is time tracking records. Confirm before deleting tasks unless the request is unambiguous.
- "complete"/"done" → status `Finished` (or `Done` if that's the card's existing convention). "ongoing"/"working on" → a card with a running time tracker (`end_time IS NULL`), not the `In progress` status. "backlog" → `Backlog`.
- When listing tasks, exclude terminal-status cards (`Done`, `Finished`) unless asked. Default to the top 10 rows and show the total count.
- Show to-dos as a checkbox list: checked = task finished, unchecked = the rest. Number listed rows from 1 so the user can refer to a row by index ("do number 3"); keep numbering stable within a listing.
- "How long did I spend on X?" → query only, create nothing.
- Page content always via the `page` subcommand — never fetch or mutate blocks via ad-hoc snippets.
- If data looks stale (>1 day since last sync), suggest running sync first. If a query returns no results, say so rather than showing an empty table.
