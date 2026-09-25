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

## Running Python

Run all Python through `uv run`, never a hard-coded interpreter path.

The uv venv lives at the **project root** — the skills installation folder / pi-package root — i.e. `<root>/.venv`. Detect that root (the directory containing `pyproject.toml` and `.venv`, found by walking up from the current working directory) and run scripts from it via `uv run`; `uv run` auto-resolves `<root>/.venv` and works from any subdirectory. Do not assume the current working directory is the project root.

## Notion API

All Notion interactions go through the `notion-client` Python library (`from notion_client import Client`) — no raw HTTP calls. When you hit issues invoking the Notion API (unexpected errors, deprecated routes, changed behavior), check the latest reference: https://developers.notion.com/reference/intro

## Connection

Read `NOTION_TOKEN` and `DATABASE_URL` from the project's `.env` file. `.env` is *not necessarily in the current working directory* — walk up from `cwd` to the nearest `.env`. This assumes this project's `.env` is the nearest one up the tree (don't keep an unrelated `.env` in an ancestor of this project). Use these boilerplates instead of redefining them per skill.

### Shared loader (finds nearest .env)

```python
from pathlib import Path

def load_env() -> dict:
    # Nearest .env in cwd or any ancestor directory.
    here = Path.cwd()
    env_file = next((d / ".env" for d in [here, *here.parents] if (d / ".env").is_file()), None)
    if env_file is None:
        raise FileNotFoundError(f"No .env found in {here} or any parent directory")
    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env
```

### Postgres (local mirror)

```python
import psycopg

env = load_env()
url = env['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://', 1)
conn = psycopg.connect(url)
```

### Notion client

```python
from notion_client import Client

env = load_env()
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

## Time Zone

Use the system's local time zone — never hard-code an offset (e.g. `+08:00`). Detect it at runtime:

```python
from datetime import datetime

def local_now():
    """Current time in the system's local time zone (tz-aware, correct offset/DST)."""
    return datetime.now().astimezone()
```

When writing `start_time`/`end_time` to Notion, use `local_now().isoformat()` so the stored value carries the correct offset.

## Time Display

When displaying times (task entries, time tracking, due dates, etc.), show them in the user's local time zone, not UTC. Use `local_now()` (above) rather than assuming a fixed zone.
