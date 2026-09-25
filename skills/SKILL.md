---
name: notion-sync
description: Local mirror of Notion databases synced to Postgres for task management. Use when the user asks about their tasks, time entries, records, projects, or wants to sync, track, or report on their work.
---

# Notion Sync

Local mirror of Notion databases synced to Postgres for task management.

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

## Time Display

When displaying times (task entries, time tracking, due dates, etc.), show them in the user's local time zone, not UTC. Detect the local time zone at runtime (e.g. the system zone) rather than assuming a fixed one.
