# Shared Conventions

All skills in this project follow the conventions defined here.

## Listing Database Rows

When listing database rows (tasks, records, projects, time entries, etc.), number them starting from 1 so the user can refer to any row by its index (e.g., "do number 3"). Keep the numbering stable within a single listing.

## Card Title Preload

At the start of a session, load the last-used card titles into context so the user's loose references can be fuzzy-matched:

```bash
uv run python scripts/load_recent_cards.py
```

Re-run it mid-session if you need a fresher set. The limit is configurable via `RECENT_CARDS_LIMIT` in `.env` (default 20).

## Notion API

All Notion interactions go through the `notion-client` Python library (`from notion_client import Client`) — no raw HTTP calls. When you hit issues invoking the Notion API (unexpected errors, deprecated routes, changed behavior), check the latest reference: https://developers.notion.com/reference/intro

## Connection

Read `NOTION_TOKEN` and `DATABASE_URL` from the project's `.env` file (same directory as `pyproject.toml`). Use these boilerplates instead of redefining them per skill.

### Postgres (local mirror)

```python
import psycopg
from pathlib import Path

env = dict(line.split('=', 1) for line in Path('.env').read_text().strip().splitlines() if '=' in line)
url = env['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://', 1)
conn = psycopg.connect(url)
```

### Notion client

```python
from notion_client import Client

env = dict(line.split('=', 1) for line in Path('.env').read_text().strip().splitlines() if '=' in line)
notion = Client(auth=env['NOTION_TOKEN'])   # one client per run; call notion.close() when done
TIME_TRACKING_DB = env['NOTION_DB_TIME_TRACKING']
```

### Finding Task IDs

To find a task by name, query the local Postgres mirror first:

```python
with psycopg.connect(url) as conn:
    row = conn.execute(
        "SELECT id, name FROM tasks WHERE name ILIKE %s AND deleted_at IS NULL LIMIT 1",
        (f"%{name}%",)
    ).fetchone()
```

## Auto-Sync After Mutations

After each successful Notion mutation (create/update/archive in any skill), automatically run an incremental sync to keep the local Postgres mirror up to date:

```bash
uv run python sync/sync.py
```

## Time Display

When displaying times (task entries, time tracking, due dates, etc.), show them in the user's local time zone, not UTC. Detect the local time zone at runtime (e.g. the system zone) rather than assuming a fixed one.
