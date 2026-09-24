# AGENTS.md

## Listing Database Rows

When listing database rows (tasks, records, projects, time entries, etc.), number them starting from 1 so the user can refer to any row by its index (e.g., "do number 3"). Keep the numbering stable within a single listing.

## Notion API

When you hit issues invoking the Notion API (unexpected errors, deprecated routes, changed behavior), check the latest reference: https://developers.notion.com/reference/intro — the skill docs may lag behind.

## GitHub Operations

All GitHub operations (push, pull, remote setup, PRs, etc.) should be done with the `gh` CLI tool, not raw `git remote`/`git push` commands.
