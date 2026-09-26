"""Shared plumbing for the notion_cards subcommand modules.

Environment loading, mirror access, task/project resolution, and Notion
property helpers used across subcommands.
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

# Make the sync engine importable (sync/sync.py is the `sync` module).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "sync"))

from notion_client import Client

import sync

UUID_RE = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.I)

DEFAULT_RECENT_LIMIT = 20
RECENT_CARDS_LIMIT_KEY = "RECENT_CARDS_LIMIT"


# --- Environment ------------------------------------------------------------


def load_env() -> dict[str, str]:
    """Read KEY=VALUE pairs from the nearest .env (cwd or an ancestor)."""
    here = Path.cwd()
    env_file = next(
        (d / ".env" for d in [here, *here.parents] if (d / ".env").is_file()),
        None,
    )
    if env_file is None:
        raise FileNotFoundError(f"No .env found in {here} or any parent directory")
    env = {}
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def local_now() -> datetime:
    """Current time in the system's local time zone (tz-aware, correct offset/DST)."""
    return datetime.now().astimezone()


def require(env: dict[str, str], *keys: str) -> None:
    missing = [k for k in keys if k not in env]
    if missing:
        sys.exit(f"Missing {', '.join(missing)} in .env")


# --- Mirror / sync ----------------------------------------------------------


def connect(env: dict[str, str]):
    """Open the mirror (schema initialized idempotently)."""
    conn = sync.connect(sync.db_path(env))
    sync.init_schema(conn)
    return conn


def auto_sync(env: dict[str, str]) -> None:
    """Incremental in-process sync after a mutation, so the mirror stays consistent."""
    client = Client(auth=env["NOTION_TOKEN"])
    try:
        conn = connect(env)
        try:
            sync.sync_all(client, env, conn)
            conn.commit()
        finally:
            conn.close()
    finally:
        client.close()
    print("Mirror synced.")


# --- Task / project resolution ---------------------------------------------


def find_task(conn, query: str) -> tuple[str, str]:
    """Resolve a task to (page_id, name) by UUID, exact name, then unique substring."""
    if UUID_RE.match(query):
        row = conn.execute(
            "SELECT id, name FROM tasks WHERE id = ? AND deleted_at IS NULL", (query,)
        ).fetchone()
        if row:
            return row[0], row[1]
        sys.exit(f"No task with id {query}.")

    exact = conn.execute(
        "SELECT id, name FROM tasks WHERE name = ? AND deleted_at IS NULL", (query,)
    ).fetchall()
    if len(exact) == 1:
        return exact[0][0], exact[0][1]
    if len(exact) > 1:
        sys.exit(f"Ambiguous task name '{query}': {[r[1] for r in exact]}")

    like = conn.execute(
        "SELECT id, name FROM tasks WHERE lower(name) LIKE lower(?) AND deleted_at IS NULL ORDER BY name",
        (f"%{query}%",),
    ).fetchall()
    if len(like) == 1:
        return like[0][0], like[0][1]
    if not like:
        sys.exit(f"No task matching '{query}'.")
    sys.exit(f"Ambiguous task name '{query}': {[r[1] for r in like]}")


def find_project(conn, query: str) -> str:
    """Resolve a project to a page id against the local mirror."""
    if UUID_RE.match(query):
        row = conn.execute(
            "SELECT id FROM projects WHERE id = ? AND deleted_at IS NULL", (query,)
        ).fetchone()
        if row:
            return row[0]
        sys.exit(f"No project with id {query}.")

    exact = conn.execute(
        "SELECT id, name FROM projects WHERE name = ? AND deleted_at IS NULL", (query,)
    ).fetchall()
    if len(exact) == 1:
        return exact[0][0]
    if len(exact) > 1:
        sys.exit(f"Ambiguous project name '{query}': {[r[1] for r in exact]}")

    like = conn.execute(
        "SELECT id, name FROM projects WHERE lower(name) LIKE lower(?) AND deleted_at IS NULL ORDER BY name",
        (f"%{query}%",),
    ).fetchall()
    if len(like) == 1:
        return like[0][0]
    if not like:
        sys.exit(f"No project matching '{query}'. (Projects must already exist.)")
    sys.exit(f"Ambiguous project name '{query}': {[r[1] for r in like]}")


# --- Notion property helpers -------------------------------------------------


def build_properties(
    name: str,
    status: str | None = None,
    due: str | None = None,
    project_id: str | None = None,
    tags: list[str] | None = None,
    priority: str | None = None,
    description: str | None = None,
) -> dict:
    """Assemble the Notion `properties` payload.

    ``None`` means "not passed" (field omitted); an empty string clears the
    field. Tags/project are replaced wholesale.
    """
    props: dict = {"Name": {"title": [{"text": {"content": name}}]}}
    if status is not None:
        props["Status"] = {"select": {"name": status} if status else None}
    if due is not None:
        props["Due Date"] = {"date": {"start": due} if due else None}
    if project_id is not None:
        props["Projects"] = {"relation": [] if not project_id else [{"id": project_id}]}
    if tags is not None:
        props["Tags"] = {"multi_select": [{"name": t} for t in tags]}
    if priority is not None:
        props["Priority"] = {"select": {"name": priority} if priority else None}
    if description is not None:
        props["Description"] = {
            "rich_text": [{"text": {"content": description}}] if description else []
        }
    return props


def validate_selects(notion: Client, ds_id: str, properties: dict) -> None:
    """Exit if a provided Status/Priority value is not a valid option for the DB."""
    schema = cast(dict[str, Any], notion.data_sources.retrieve(data_source_id=ds_id))["properties"]
    for prop in ("Status", "Priority"):
        select = properties.get(prop, {}).get("select")
        name = select.get("name") if select else None
        if not name:
            continue
        options = [o["name"] for o in schema.get(prop, {}).get("select", {}).get("options", [])]
        if options and name not in options:
            sys.exit(f"Unknown {prop.lower()} '{name}'. Options: {options}")


def parse_tags(value: str | None) -> list[str] | None:
    """Split a comma-separated tags value; None means "not passed"."""
    if value is None:
        return None
    return [t.strip() for t in value.split(",") if t.strip()]


def rich_text(text: str) -> list[dict]:
    """A single-paragraph rich_text payload for comments/blocks."""
    return [{"type": "text", "text": {"content": text}}]
