# notion-todo

**Your tasks live in Notion — your coding agent just treats them as a first-class part of your workflow.** `notion-todo` wires your agent straight into your Notion task system: create, modify, and finish tasks, log and summarize time, and query your tasks, projects, and records. A fast local SQLite mirror stays in sync automatically, so answers come back instantly and every action keeps your data consistent.

## Installation

1. **Install [UV](https://docs.astral.sh/uv/)** (skip if you already have it):
   ```bash
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # ...or via Homebrew
   brew install uv
   ```

2. **Environment** (`.env` in the project root — the runner also falls back to `$HOME/.env`) — a complete example:
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
   # Optional: where the SQLite mirror lives (default: mirror.sqlite in the project root)
   # MIRROR_PATH=/path/to/mirror.sqlite
   # Optional: how many recent cards to preload for fuzzy-matching (default 20)
   # RECENT_CARDS_LIMIT=20
   ```

3. **Install the skill** where your agent auto-discovers skills so it can find it without you asking. This skill follows the [Agent Skills](https://agentskills.io) standard, so a symlink into the agent's skills directory is all that's needed:

   | Agent | Personal skills dir | Project skills dir |
   |-------|--------------------|--------------------|
   | Claude Code | `~/.claude/skills/` | `.claude/skills/` |
   | pi | `~/.pi/agent/skills/` | `.pi/skills/` |
   | Codex | `~/.codex/skills/` | — |
   | Any Agent-Skills-standard agent | `~/.agents/skills/` | `.agents/skills/` |

   ```bash
   # Example: install for Claude Code (personal)
   mkdir -p ~/.claude/skills
   ln -s "$PWD/skills/notion-todo" ~/.claude/skills/notion-todo
   ```

No server is needed — the mirror is a SQLite file created on the first sync (by default at `mirror.sqlite` in the project root).

## Creating the Notion Databases

Setting up a fresh Notion workspace? Use the provisioning script to create all four databases with every relation, rollup, and formula already wired to match what the sync expects.

### Prerequisites

- Dependencies installed and `.env` configured (see Installation above).
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

## Usage (via coding agent skills)

The `skills/` directory contains the agent skill that defines how to interact with your data:

| Skill | What it does |
|-------|-------------|
| `notion-todo` | The single skill for everything: sync, create/modify/delete tasks, log and summarize time, query tasks/records/projects, and generate reports |

You interact with this project through your coding agent. Examples:

- "What's on my plate today?"
- "What's due this week?"
- "Add a task: fix the login bug, due tomorrow, high priority"
- "Mark 'Book dentist' as done"
- "Move 'Write report' to This Month"
- "Add a project called 'Website Redesign'"
- "What projects am I active on?"
- "Log 30 minutes on 'Learn Rust'"
- "Start the time tracker on 'Learn Rust', I'm reading the Rust book"
- "Stop all time trackers"
- "What did I spend time on this week?"
- "Show a report of time spent by project"
- "Show all records tagged 'Chengdu'"
- "Find the record for the hotel I stayed at in Tokyo"
- "Add a comment to 'Book dentist': rescheduled to Friday"
- "Add a note under 'Book dentist' with the dentist's phone number"
- "Sync my tasks from Notion"
- "I updated some cards in Notion, refresh the local mirror"
- "Run a full sync"

After any mutations via the CLI, the mirror is already up to date. If you edit cards directly in Notion (outside the CLI), run a sync to refresh the local mirror. Note: comments and page content are not part of the mirror, so those edits need no sync.

## Development

Quality gates are driven from the `Makefile`:

```bash
make check     # ruff lint + pyright type-check
make test      # pytest with coverage (enforced 90% floor)
```

Install the pre-push gate (runs `check` + `test`, blocks the push if anything fails):

```bash
make install-hooks
```

### Card CLI

`scripts/notion_cards.py` is the single surface for creating, modifying, deleting, time-tracking, and annotating cards (comments, page content). Every mutation auto-syncs the mirror, so one command always leaves local data consistent.

```bash
# Create a task (only the fields you pass are set)
uv run python scripts/notion_cards.py create "Book dentist appointment" \
    --status "This Week" --due 2026-10-01 --project Life --tags Life,Urgent \
    --priority 3 --description "Bring toothbrush"

# Modify a task (empty value clears a field)
uv run python scripts/notion_cards.py modify "Book dentist" --status "" --due ""

# Archive a task (Notion soft delete)
uv run python scripts/notion_cards.py delete "Book dentist"

# Time tracking (optional description is stored on / updates the time tracking record)
uv run python scripts/notion_cards.py start "Grandma Care" "helping with forms"   # stops any open tracker first
uv run python scripts/notion_cards.py end "wrapped up the review"                 # stops every open tracker

# Recent tasks with ids (for fuzzy-matching in agent context)
uv run python scripts/notion_cards.py recent 20

# Most frequently used tasks and projects, with ids (default 15)
uv run python scripts/notion_cards.py frequent --limit 20

# Comments (read/create/update/delete; update/delete default to the latest comment)
uv run python scripts/notion_cards.py comment "Grandma Care" read
uv run python scripts/notion_cards.py comment "Grandma Care" create "text"
uv run python scripts/notion_cards.py comment "Grandma Care" update "new text" [comment-id]
uv run python scripts/notion_cards.py comment "Grandma Care" delete [comment-id]

# Page content (read/create/update/delete; update/delete default to the last block)
uv run python scripts/notion_cards.py page "Grandma Care" read
uv run python scripts/notion_cards.py page "Grandma Care" create "text"
uv run python scripts/notion_cards.py page "Grandma Care" update "new text" [block-id]
uv run python scripts/notion_cards.py page "Grandma Care" delete [block-id]

# Sync (incremental by default; --full also soft-deletes records gone from Notion)
uv run python scripts/notion_cards.py sync [--full]
```

The optional `start` description is stored on the Time Tracking DB's `Description` property (provisioned by `create_databases.py`).

Task resolution: exact UUID, exact name, then unique substring — ambiguous matches are rejected.

Sync uses Notion's `last_edited_time` filter incrementally; soft-deletes are only detected on `--full` runs.

### Schema

See `sync/schema.sql` for the full DDL. Key design decisions:

- Notion record IDs stored as `TEXT` primary keys; timestamps as ISO-8601 strings
- `tags` is a JSON list of strings
- Formula/rollup fields (Duration, Time Spent, etc.) are computed in SQL, not stored
- Soft-delete via `deleted_at` column (records deleted in Notion are marked, not removed)
- `sync_state` table tracks the last-sync watermark per database

## Context

See `CONTEXT.md` for the domain glossary. See `docs/adr/` for recorded decisions.

## License

MIT — see [LICENSE](LICENSE).
