---
name: notion-todo
description: Manage Notion cards (tasks, time tracking) via scripts/notion_cards.py and the local SQLite mirror. Use when the user asks to sync, create/update/delete a task, log or summarize time, asks about their tasks/records/projects, or wants a report or overview.
---

# Notion Card Management

All Notion interactions go through `scripts/notion_cards.py` (auto-syncs the mirror after every mutation) and the local SQLite mirror for queries.

## Running scripts

Run the Python helper scripts through the shared runner:

```bash
bash <root>/scripts/run.sh <script-name> [args...]
```

- `<root>` is the **project root** — the directory containing `pyproject.toml` and `.venv` (the skills installation folder / pi-package root). Detect it by walking up from the current working directory; do not assume the current directory is the project root.
- The runner uses its own location to find `<root>/.venv/bin/python`, sources the nearest `.env` (cwd, then `$HOME`), and maps `<script-name>` to `<root>/scripts/<script-name>.py`.
- All script invocations in this skill use the runner (e.g. `bash <root>/scripts/run.sh notion_cards ...`). Never hard-code an interpreter path.

### Running ad-hoc Python snippets

**Only use ad-hoc snippets for mirror queries or one-off Notion API calls the CLI does not cover** (e.g. custom reports, logging a past time entry). If `notion_cards` has a subcommand for the request, use it — do not write a snippet.

Every ad-hoc snippet must run in the project venv with `.env` loaded. Do this by writing the snippet to a temporary file in `<root>/scripts/` and running it through the runner:

1. Write the snippet to `<root>/scripts/_adhoc.py`, starting from the template below.
2. Run: `bash <root>/scripts/run.sh _adhoc`
3. Delete `<root>/scripts/_adhoc.py` when done.

This guarantees the snippet uses `<root>/.venv/bin/python` and the loaded environment. Never invoke bare `python`/`uv` from an arbitrary directory for snippets.

### Template

Every ad-hoc script starts from this skeleton — copy it, keep the setup lines exactly, and replace the body. Keep the Notion client commented out (and the database ids) if the script only queries the mirror:

```python
import os
import sqlite3
import sys
from pathlib import Path

# ── SQLite mirror access ──
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sync"))
import sync
conn = sync.connect(sync.db_path(os.environ))  # FK pragma on
conn.row_factory = sqlite3.Row

# ── Notion client (uncomment only if the script calls the Notion API) ──
# from notion_client import Client
# notion = Client(auth=os.environ["NOTION_TOKEN"])
# DB_IDS = {
#     "tasks": os.environ["NOTION_DB_TASKS"],
#     "projects": os.environ["NOTION_DB_PROJECTS"],
#     "records": os.environ["NOTION_DB_RECORDS"],
#     "time_tracking": os.environ["NOTION_DB_TIME_TRACKING"],
# }

# ── Your code ──
rows = conn.execute(
    "SELECT name, status FROM tasks WHERE deleted_at IS NULL AND status != 'Done'"
).fetchall()
for row in rows:
    print(row["name"], "|", row["status"])
```

- Never modify the mirror directly — it is owned by sync; if the script mutates Notion, finish with `bash <root>/scripts/run.sh notion_cards sync`.
- Timestamps are ISO-8601 strings; `tags` is a JSON list of strings (e.g. `["a", "b"]`); filter `deleted_at IS NULL`.

## Notion API

All Notion interactions go through the `notion-client` Python library — no raw HTTP calls. When you hit issues invoking the Notion API (unexpected errors, deprecated routes, changed behavior), check the latest reference: https://developers.notion.com/reference/intro

## Connection

### .env loading

The runner already loads the nearest `.env` into the process environment. In ad-hoc snippets just use `os.environ` (e.g. `os.environ["NOTION_TOKEN"]`) — never re-parse `.env`.

### Notion client

```python
from notion_client import Client

notion = Client(auth=os.environ["NOTION_TOKEN"])
TIME_TRACKING_DB = os.environ["NOTION_DB_TIME_TRACKING"]
```

One client per run; call `notion.close()` when done.

### SQLite (local mirror)

```python
import sys
from pathlib import Path

# Make the sync engine importable (required for snippets in <root>/scripts/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sync"))
import sync

conn = sync.connect(sync.db_path(os.environ))
```

Always use `sync.db_path(os.environ)` to obtain the path (it also honors an optional `MIRROR_PATH` override in `.env`). Use `sync.connect` (not bare `sqlite3.connect`) — same path the CLI uses, with the foreign-key pragma on.

### Finding task IDs

The CLI already resolves cards (UUID → exact name → unique substring; ambiguous matches rejected). For ad-hoc mirror queries, match `tasks.name` with `lower(name) LIKE lower(?)` and `deleted_at IS NULL`.

### Time zones

Never hard-code an offset. When writing times to Notion use `datetime.now().astimezone().isoformat()`; when displaying times show the user's local time zone, not UTC.

## Card operations (CLI)

```bash
# Create (only the fields you pass are set)
bash <root>/scripts/run.sh notion_cards create <name> \
    [--status STATUS] [--due YYYY-MM-DD] [--project NAME] \
    [--tags a,b] [--priority 5] [--description TEXT]

# Modify (empty value clears a field; tags/project replaced wholesale)
bash <root>/scripts/run.sh notion_cards modify <task> \
    [--name NEW] [--status STATUS] [--due YYYY-MM-DD] [--project NAME] \
    [--tags a,b] [--priority 5] [--description TEXT]

# Delete (Notion archive — no hard delete via API)
bash <root>/scripts/run.sh notion_cards delete <task>

# Time tracking
bash <root>/scripts/run.sh notion_cards start <task>   # stops any open tracker first
bash <root>/scripts/run.sh notion_cards end            # stops every open tracker; idempotent
```

- `--project` links an existing project (name, unique substring, or UUID); it never creates one.
- **Single running tracker invariant:** at most one open tracker. `start` enforces it — never allow two open trackers.
- Every CLI mutation auto-syncs the mirror — no extra sync step.

### Comments

Read, create, update, and delete comments on a card (Notion-only; not mirrored):

```bash
bash <root>/scripts/run.sh notion_cards comment <card> read
bash <root>/scripts/run.sh notion_cards comment <card> create "text"
bash <root>/scripts/run.sh notion_cards comment <card> update "new text" [comment-id]
bash <root>/scripts/run.sh notion_cards comment <card> delete [comment-id]
```

- `update`/`delete` without a comment-id act on the card's **latest** comment.
- No sync needed — comments are not part of the local mirror.

## Sync

```bash
bash <root>/scripts/run.sh notion_cards sync          # incremental (default)
bash <root>/scripts/run.sh notion_cards sync --full   # full: also soft-deletes records gone from Notion
```

Default to incremental; only `--full` when the user explicitly asks. On schema mismatch, do NOT sync — stop and report which fields are new or missing (then update `sync/schema.sql` and `sync/sync.py`). On rate limiting (HTTP 429), wait and retry.

## Context preload

At the start of a session, load recent card titles into context so the user's loose references can be fuzzy-matched. Re-run mid-session if you need a fresher set:

```bash
bash <root>/scripts/run.sh notion_cards recent [N]           # N defaults to RECENT_CARDS_LIMIT, then 20
bash <root>/scripts/run.sh notion_cards frequent [--limit N] # N defaults to 15; tasks + projects with ids
```

`frequent` prints two lists (tasks, then projects), each row `  <id>  <name>` — use it when you need ids for mutations, queries, or project linking. If a referenced card isn't in the list, raise the limit.

## Querying (local SQLite)

Tables:
- `tasks` — id, name, tags (JSON list), status, due_date, project_id, priority, description, created_at, notion_updated_at
- `records` — id, name, tags (JSON list), project_id, summary, created_at, notion_updated_at
- `projects` — id, name, status, notion_updated_at
- `time_tracking` — id, name, task_id, start_time, end_time, status, notion_updated_at

Filter `deleted_at IS NULL` on everything. Cards tagged `hidden` are excluded from all lists by default — include them only when the user explicitly asks (filter: `tags NOT LIKE '%"hidden"%'`).

SQLite has no `EXTRACT`; compute hours as
`round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1)`.

### Common queries

**"What's on my plate today?"**
```sql
SELECT t.name, t.priority, t.due_date, p.name AS project
FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
WHERE t.status = 'Today' AND t.deleted_at IS NULL
ORDER BY t.priority DESC
```

**"What's due this week?"**
```sql
SELECT t.name, t.due_date, t.status, p.name AS project
FROM tasks t LEFT JOIN projects p ON t.project_id = p.id
WHERE t.due_date BETWEEN date('now') AND date('now', '+7 days')
  AND t.deleted_at IS NULL AND t.status != 'Done'
ORDER BY t.due_date
```

**"Show high-priority backlog"**
```sql
SELECT name, tags, due_date FROM tasks
WHERE status = 'Backlog' AND priority IS NOT NULL AND deleted_at IS NULL
ORDER BY priority DESC
```

**"What time did I spend this week?"**
```sql
SELECT tt.start_time, tt.name, t.name AS task
FROM time_tracking tt
LEFT JOIN tasks t ON t.id = tt.task_id
WHERE tt.start_time >= datetime('now', '-7 days')
  AND tt.deleted_at IS NULL
ORDER BY tt.start_time DESC
```

**"Show records tagged X"**
```sql
SELECT name, summary FROM records
WHERE tags LIKE '%"x"%' AND deleted_at IS NULL
```

**Project status overview**
```sql
SELECT p.name, p.status,
       count(t.id) AS task_count,
       sum(CASE WHEN t.status = 'Done' THEN 1 ELSE 0 END) AS done_count
FROM projects p
LEFT JOIN tasks t ON t.project_id = p.id AND t.deleted_at IS NULL
WHERE p.deleted_at IS NULL
GROUP BY p.name, p.status
ORDER BY p.status
```

**Default card list** (Title, Project, Status, Total Time — top 10, show total count)
```sql
SELECT t.name, p.name, t.status,
       round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1) AS total_hours
FROM tasks t
LEFT JOIN projects p ON p.id = t.project_id
LEFT JOIN time_tracking tt ON tt.task_id = t.id AND tt.deleted_at IS NULL AND tt.end_time IS NOT NULL
WHERE t.deleted_at IS NULL
GROUP BY t.id, p.name
ORDER BY t.created_at
LIMIT 10
```

### Page content

Page body content (paragraphs, headings, lists) is **not** synced locally — `description` is the only stored text. Use the CLI for **all** page content operations (read, create, update, delete) — never fetch or mutate blocks via ad-hoc API snippets:

```bash
bash <root>/scripts/run.sh notion_cards page <card> read
bash <root>/scripts/run.sh notion_cards page <card> create "text"     # appends a paragraph
bash <root>/scripts/run.sh notion_cards page <card> update "new text" [block-id]
bash <root>/scripts/run.sh notion_cards page <card> delete [block-id]
```

- `update`/`delete` without a block-id act on the card's **last** block.
- `update` replaces a block's text (text blocks only: paragraph, headings, list items, to-do, callout, quote).
- No sync needed — page content is not part of the local mirror.

## Time tracking

### Log a past time entry against a task

Create via the API (start_time/end_time are ISO 8601 with the user's local timezone, e.g. `2026-09-22T09:00:00+08:00`), then sync:

```python
def log_time(task_id: str, start_time: str, end_time: str, name: str = None):
    properties = {
        "Name": {"title": [{"text": {"content": name or "Time entry"}}]},
        "Start Time": {"date": {"start": start_time}},
        "End Time": {"date": {"start": end_time}},
        "Status": {"select": {"name": "Stopped"}},
        "Tasks": {"relation": [{"id": task_id}]},
    }
    notion.pages.create(
        parent={"database_id": TIME_TRACKING_DB}, properties=properties
    )
```

Patterns: "Log 30 minutes on X" → start=now-30min, end=now. "Log 1 hour on X this morning" → start=9am, end=10am.

### Summaries

**Time spent today**
```sql
SELECT t.name AS task,
       round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1) AS hours
FROM time_tracking tt
JOIN tasks t ON t.id = tt.task_id
WHERE date(tt.start_time) = date('now')
  AND tt.deleted_at IS NULL AND tt.end_time IS NOT NULL
GROUP BY t.name
ORDER BY hours DESC
```

**Time spent this week per project**
```sql
SELECT p.name AS project,
       round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1) AS hours
FROM time_tracking tt
JOIN tasks t ON t.id = tt.task_id
LEFT JOIN projects p ON p.id = t.project_id
WHERE tt.start_time >= datetime('now', '-7 days')
  AND tt.deleted_at IS NULL AND tt.end_time IS NOT NULL
GROUP BY p.name
ORDER BY hours DESC
```

**Total time per task (all time)**
```sql
SELECT t.name, count(*) AS entries,
       round(sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24), 1) AS total_hours
FROM time_tracking tt
JOIN tasks t ON t.id = tt.task_id
WHERE tt.deleted_at IS NULL AND t.deleted_at IS NULL AND tt.end_time IS NOT NULL
GROUP BY t.name
HAVING sum((julianday(tt.end_time) - julianday(tt.start_time)) * 24) > 0
ORDER BY total_hours DESC
LIMIT 20
```

## Reports

**Daily summary** ("what did I do today?") — active tasks today:
```sql
SELECT name, status, priority FROM tasks
WHERE status = 'Today' AND deleted_at IS NULL
```
plus the "time spent today" query above.

**Weekly review** ("what was my week like?")
```sql
SELECT name FROM tasks
WHERE status = 'Done'
  AND notion_updated_at >= datetime('now', '-7 days')
  AND deleted_at IS NULL;

SELECT count(*) FROM tasks WHERE status = 'Backlog' AND deleted_at IS NULL;
```
plus the "time spent this week per project" query above.

**Workload overview** ("what's on my plate?")
```sql
SELECT status, count(*) AS count
FROM tasks
WHERE deleted_at IS NULL AND status != 'Done'
GROUP BY status
ORDER BY
  CASE status
    WHEN 'Today' THEN 1
    WHEN 'This Week' THEN 2
    WHEN 'This Month' THEN 3
    WHEN 'Blocked' THEN 4
    WHEN 'In progress' THEN 5
    ELSE 6
  END;
```

**Project health** — use the "Project status overview" query above.

### Report output format

- Tables for structured data, bullets for narrative; include totals ("Total: 6.5 hours this week")
- Flag anomalies: tasks stuck in "Today" >1 week, blocked items with no update
- Bold key numbers, group by priority, keep scannable

## Rules

- **Prefer the CLI.** Every operation covered by `notion_cards` (create, modify, delete, start, end, sync, comment, page, recent, frequent) is already implemented — do NOT write ad-hoc code for those.
- **Ad-hoc is for queries only** (reading the local mirror) or for one-off Notion API calls with no CLI equivalent (e.g. logging a past time entry). If a CLI subcommand covers the request, use it.
- Show to-do content as a checkbox list: a checked box for each to-do whose task is finished, an unchecked box for the rest, so the user can see at a glance which tasks are done
- When listing database rows (tasks, records, projects, time entries), number them starting from 1 so the user can refer to any row by its index (e.g. "do number 3"); keep the numbering stable within a single listing
- Always confirm before creating a new Notion entity (task, project, record, comment, page block) — the only exception is time tracking records, which you may create without asking
- Always confirm before deleting tasks unless the request is unambiguous
- "complete"/"done" → set status to `Finished` (or `Done` if that's the card's existing convention)
- "ongoing"/"working on" → a card with a running time tracker (`time_tracking` row with `end_time IS NULL`), not the `In progress` status
- "backlog" → `status = 'Backlog'`
- When listing tasks, exclude terminal-status cards (`Done` and `Finished`) unless the user explicitly asks
- Default task lists to the top 10 rows (show the total count)
- "How long did I spend on X?" → query, don't create anything
- Page content: always via the `page` subcommand (above); never add page blocks to the local mirror
- If data looks stale (>1 day since last sync), suggest running sync first
- If a query returns no results, say so rather than showing an empty table
