---
name: notion-sync
description: Sync Notion databases to the local SQLite mirror. Use when the user asks to sync, refresh, or update their local task data.
---

# Notion Sync

> Follow shared conventions: `../conventions.md`

Run the sync to pull changes from Notion into the local SQLite mirror.

## Usage

```bash
# Default: incremental
uv run python scripts/notion_cards.py sync

# Full (only when explicitly requested by the user)
uv run python scripts/notion_cards.py sync --full
```

## Behavior

- **Incremental** (default): Only fetches records updated since last sync. Fast.
- **Full** (`--full`): Fetches all records and soft-deletes any that no longer exist in Notion.

## Schema Mismatch

If the Notion database schema has changed (fields added/removed), the sync will refuse and list which fields are new or missing. In that case:

1. Tell the user what changed in Notion
2. Update `sync/schema.sql` (SQLite DDL) and `sync/sync.py` (field parsing) to match
3. Re-run the sync

## After Sync

- Suggest running a query skill if the user was about to do something with the data
- Report the number of records synced

## Rules

- Default to incremental; only use `--full` when the user explicitly asks for a full sync
- If sync fails due to rate limiting (HTTP 429), wait and retry
- If schema mismatch occurs, do NOT attempt to sync — stop and report
