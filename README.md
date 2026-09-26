# notion-sync

Local mirror of your Notion task management system, synced to SQLite for fast querying and agent-driven interaction.

## Databases Synced

| Database | Purpose |
|----------|---------|
| Tasks | Your todo items with status, priority, due dates |
| Projects | Grouping containers for tasks and records |
| Records | General reference notes (contacts, places, reading, etc.) |
| Time Tracking | Time entries logged against tasks |

## Setup

1. **Dependencies** (managed by UV):
   ```bash
   uv sync
   ```

2. **Environment** (`.env`) — a complete example:
   ```
   # Your Notion integration token
   NOTION_TOKEN=ntn_your_token
   # The page the four databases live under (see Creating the Notion Databases)
   NOTION_PARENT_PAGE=1a2b3c4c5d6e7f8a9b0c1d2e3f4a5b6c
   # Filled in automatically by scripts/create_databases.py after it runs
   NOTION_DB_PROJECTS=00000000-0000-0000-0000-000000000000
   NOTION_DB_RECORDS=00000000-0000-0000-0000-000000000000
   NOTION_DB_TASKS=00000000-0000-0000-0000-000000000000
   NOTION_DB_TIME_TRACKING=00000000-0000-0000-0000-000000000000
   # Optional: where the SQLite mirror lives (default: .notion-sync/mirror.sqlite)
   # MIRROR_PATH=/path/to/mirror.sqlite
   # Optional: how many recent cards to preload for fuzzy-matching (default 20)
   # RECENT_CARDS_LIMIT=20
   ```

No server is needed — the mirror is a SQLite file created on the first sync (the table schema is provisioned automatically; by default at `.notion-sync/mirror.sqlite` under the project root).

## Creating the Notion Databases

Setting up a fresh Notion workspace? Use the provisioning script to create all four databases with every relation, rollup, and formula already wired to match what the sync expects.

### Prerequisites

- Dependencies installed and `.env` configured (see Setup above).
- Add `NOTION_PARENT_PAGE` to `.env` — the ID of the Notion page you want the databases created under.
  - It's the trailing part of the page's URL, e.g. in `https://www.notion.so/My-Workspace/My-Page-1a2b3c…` it is `1a2b3c…`. Notion accepts the 32-hex-char form (no dashes).

### Run

```bash
uv run python scripts/create_databases.py
```

What it does:

1. Validates that `NOTION_PARENT_PAGE` exists and isn't archived.
2. Refuses to run if a **Tasks** database already exists under that page (a guard against double-provisioning).
3. Creates **Projects**, **Records**, **Tasks**, and **Time Tracking DB**.
4. Wires the cross-database properties in dependency order: relations (Tasks↔Projects, Time Tracking↔Tasks), then the Time Tracking rollups and formulas (`Duration`, `Weekly Duration`), then the Tasks rollups (`Time Spent`, `Weekly Time Spent`).
5. Writes the four `NOTION_DB_*` IDs back into `.env`.

### Then sync

```bash
uv run python scripts/notion_cards.py sync --full
```

This seeds the local mirror (the table schema is created automatically on the first sync).

### Notes

- The three `Status` columns are created as **select** — Notion's API cannot create `status` columns. They carry the same options (just no groups), and the sync reads them identically.
- Re-running is safe only after archiving the existing databases; while a `Tasks` database is present under the parent page the script will refuse to proceed.

## Card CLI

`scripts/notion_cards.py` is the single surface for creating, modifying, deleting, and time-tracking cards. Every mutation auto-syncs the mirror, so one command always leaves local data consistent.

```bash
# Create a task (only the fields you pass are set)
uv run python scripts/notion_cards.py create "Book dentist appointment" \
    --status "This Week" --due 2026-10-01 --project Life --tags Life,Urgent

# Modify a task (empty value clears a field)
uv run python scripts/notion_cards.py modify "Book dentist" --status "" --due ""

# Archive a task (Notion soft delete)
uv run python scripts/notion_cards.py delete "Book dentist"

# Time tracking
uv run python scripts/notion_cards.py start "Grandma Care"   # stops any open tracker first
uv run python scripts/notion_cards.py end                    # stops every open tracker

# Recent card titles (for fuzzy-matching in agent context)
uv run python scripts/notion_cards.py recent [N]

# Sync (incremental by default)
uv run python scripts/notion_cards.py sync [--full]
```

Task resolution: exact UUID, exact name, then unique substring — ambiguous matches are rejected.

## Sync

```bash
# Full sync (first run, or after major changes in Notion)
uv run python scripts/notion_cards.py sync --full

# Incremental sync (picks up changes since last sync)
uv run python scripts/notion_cards.py sync
```

Incremental sync uses Notion's `last_edited_time` filter. Soft-deletes are only detected on `--full` runs.

## Usage (via coding agent skills)

The `skills/` directory contains agent skill files that define how to interact with your data:

| Skill | What it does |
|-------|-------------|
| `notion-sync` | The single skill for everything: sync, create/modify/delete tasks, log and summarize time, query tasks/records/projects, and generate reports |

You interact with this project through your coding agent. Examples:

- "What's on my plate today?"
- "Add a task: fix the login bug, due tomorrow"
- "Log 30 minutes on 'Learn Rust'"
- "What did I spend time on this week?"
- "Show all records tagged 'Chengdu'"

After any mutations via the CLI, the mirror is already up to date. After direct Notion API mutations (e.g. ad-hoc page edits), run a sync to refresh the local mirror.

## Schema

See `sync/schema.sql` for the full DDL. Key design decisions:

- Notion record IDs stored as `TEXT` primary keys; timestamps as ISO-8601 strings
- `tags` is a JSON list of strings
- Formula/rollup fields (Duration, Time Spent, etc.) are computed in SQL, not stored
- Soft-delete via `deleted_at` column (records deleted in Notion are marked, not removed)
- `sync_state` table tracks the last-sync watermark per database

## Context

See `CONTEXT.md` for the domain glossary. See `docs/adr/` for recorded decisions.
