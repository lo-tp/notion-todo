"""Unit tests for scripts/notion_cards.py.

Database-touching helpers run against a temporary SQLite database (see the
``test_db`` fixture). Notion calls are exercised by mocking the module-level
:class:`~notion_client.Client` factory.
"""

import sys
import uuid
from types import SimpleNamespace
from unittest import mock

import pytest

import notion_cards

# --- load_env / local_now / require ------------------------------------------


def test_load_env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "NOTION_TOKEN=tok\n# a comment\nNOTION_DB_TASKS=db\n\n"
    )
    monkeypatch.chdir(tmp_path)
    assert notion_cards.load_env() == {"NOTION_TOKEN": "tok", "NOTION_DB_TASKS": "db"}


def test_load_env_walks_up_to_parent(tmp_path, monkeypatch):
    # .env lives in a parent of the cwd, not in the cwd itself.
    (tmp_path / ".env").write_text("A=1\n")
    subdir = tmp_path / "nested" / "deeper"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    assert notion_cards.load_env() == {"A": "1"}


def test_local_now_is_tz_aware():
    assert notion_cards.local_now().tzinfo is not None


def test_require_exits_on_missing():
    with pytest.raises(SystemExit) as ei:
        notion_cards.require({"A": "1"}, "A", "B")
    assert "B" in ei.value.args[0]


# --- task / project resolution -----------------------------------------------


def _insert_task(test_db, name, deleted=False):
    tid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO tasks (id, name, notion_updated_at, deleted_at) VALUES (?, ?, ?, ?)",
        (tid, name, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z" if deleted else None),
    )
    test_db.commit()
    return tid


def _insert_project(test_db, name, deleted=False):
    pid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO projects (id, name, notion_updated_at, deleted_at) VALUES (?, ?, ?, ?)",
        (pid, name, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z" if deleted else None),
    )
    test_db.commit()
    return pid


# --- find_task ---------------------------------------------------------------


def test_find_task_by_uuid(test_db):
    tid = _insert_task(test_db, "Grandma Care")
    assert notion_cards.find_task(test_db, tid) == (tid, "Grandma Care")


def test_find_task_uuid_not_found_exits(test_db):
    with pytest.raises(SystemExit):
        notion_cards.find_task(test_db, str(uuid.uuid4()))


def test_find_task_exact_name(test_db):
    tid = _insert_task(test_db, "Grandma Care")
    assert notion_cards.find_task(test_db, "Grandma Care")[0] == tid


def test_find_task_ambiguous_exact_exits(test_db):
    _insert_task(test_db, "Duplicate")
    _insert_task(test_db, "Duplicate")
    with pytest.raises(SystemExit):
        notion_cards.find_task(test_db, "Duplicate")


def test_find_task_unique_substring(test_db):
    tid = _insert_task(test_db, "Grandma Care")
    _insert_task(test_db, "Other Task")
    page_id, name = notion_cards.find_task(test_db, "Grandma")
    assert (page_id, name) == (tid, "Grandma Care")


def test_find_task_ambiguous_substring_exits(test_db):
    _insert_task(test_db, "Care A")
    _insert_task(test_db, "Care B")
    with pytest.raises(SystemExit):
        notion_cards.find_task(test_db, "Care")


def test_find_task_no_match_exits(test_db):
    _insert_task(test_db, "Something Else")
    with pytest.raises(SystemExit):
        notion_cards.find_task(test_db, "nonexistent-zzz")


def test_find_task_excludes_deleted(test_db):
    _insert_task(test_db, "Deleted Task", deleted=True)
    with pytest.raises(SystemExit):
        notion_cards.find_task(test_db, "Deleted")


# --- find_project --------------------------------------------------------------


def test_find_project_exact(test_db):
    pid = _insert_project(test_db, "Life")
    assert notion_cards.find_project(test_db, "Life") == pid


def test_find_project_by_uuid(test_db):
    pid = _insert_project(test_db, "Life")
    assert notion_cards.find_project(test_db, pid) == pid


def test_find_project_ambiguous_substring_exits(test_db):
    _insert_project(test_db, "Life")
    _insert_project(test_db, "Life Hacks")
    with pytest.raises(SystemExit):
        notion_cards.find_project(test_db, "if")


def test_find_project_no_match_exits(test_db):
    with pytest.raises(SystemExit):
        notion_cards.find_project(test_db, "nonexistent")


# --- build_properties / parse_tags / validate_selects -------------------------


def test_build_properties_minimal():
    props = notion_cards.build_properties("Task A")
    assert props == {"Name": {"title": [{"text": {"content": "Task A"}}]}}


def test_build_properties_all_fields():
    props = notion_cards.build_properties(
        "Task A",
        status="This Week",
        due="2026-10-01",
        project_id="proj-1",
        tags=["Life", "Urgent"],
        priority="5",
        description="details",
    )
    assert props["Name"]["title"][0]["text"]["content"] == "Task A"
    assert props["Status"] == {"select": {"name": "This Week"}}
    assert props["Due Date"] == {"date": {"start": "2026-10-01"}}
    assert props["Projects"] == {"relation": [{"id": "proj-1"}]}
    assert props["Tags"] == {"multi_select": [{"name": "Life"}, {"name": "Urgent"}]}
    assert props["Priority"] == {"select": {"name": "5"}}
    assert props["Description"] == {"rich_text": [{"text": {"content": "details"}}]}


def test_build_properties_clear_semantics():
    props = notion_cards.build_properties(
        "Task A", status="", due="", project_id="", tags=[], priority="", description=""
    )
    assert props["Status"] == {"select": None}
    assert props["Due Date"] == {"date": None}
    assert props["Projects"] == {"relation": []}
    assert props["Tags"] == {"multi_select": []}
    assert props["Priority"] == {"select": None}
    assert props["Description"] == {"rich_text": []}


def test_parse_tags():
    assert notion_cards.parse_tags(None) is None
    assert notion_cards.parse_tags("") == []
    assert notion_cards.parse_tags("a, b ,c,") == ["a", "b", "c"]


def _mock_notion(options_by_prop):
    client = mock.MagicMock()
    client.data_sources.retrieve.return_value = {
        "properties": {
            prop: {"select": {"options": [{"name": o} for o in opts]}}
            for prop, opts in options_by_prop.items()
        }
    }
    return client


def test_validate_selects_accepts_known():
    notion = _mock_notion({"Status": ["This Week", "Today"]})
    # Should not raise.
    notion_cards.validate_selects(notion, "ds", {"Status": {"select": {"name": "This Week"}}})


def test_validate_selects_rejects_unknown_status():
    notion = _mock_notion({"Status": ["This Week", "Today"]})
    with pytest.raises(SystemExit):
        notion_cards.validate_selects(notion, "ds", {"Status": {"select": {"name": "Nope"}}})


def test_validate_selects_skips_absent_and_cleared_fields():
    notion = _mock_notion({"Status": ["This Week"], "Priority": ["5"]})
    # Cleared (None) values and absent fields are skipped.
    notion_cards.validate_selects(
        notion, "ds", {"Status": {"select": None}, "Name": {"title": []}}
    )


# --- open_trackers / stop_all_running / start_tracking ------------------------


def _insert_open_tracker(test_db, task_id):
    tid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO time_tracking (id, name, task_id, start_time, status, notion_updated_at) "
        "VALUES (?, 'open', ?, ?, 'Ing', ?)",
        (tid, task_id, "2026-01-02T09:00:00Z", "2026-01-02T09:00:00Z"),
    )
    test_db.commit()
    return tid


def test_open_trackers_returns_only_open_rows(test_db):
    task = _insert_task(test_db, "open task")
    _insert_open_tracker(test_db, task)
    # A closed tracker must not come back.
    closed = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO time_tracking (id, name, task_id, start_time, end_time, status, notion_updated_at) "
        "VALUES (?, 'closed', ?, ?, ?, 'Stopped', ?)",
        (closed, task, "2026-01-01T09:00:00Z", "2026-01-01T10:00:00Z", "2026-01-01T10:00:00Z"),
    )
    test_db.commit()

    rows = notion_cards.open_trackers(test_db)
    assert len(rows) == 1
    assert rows[0][1] == "open task"


def test_stop_all_running_updates_each_open_tracker(test_db):
    task = _insert_task(test_db, "open task")
    tid = _insert_open_tracker(test_db, task)
    notion = mock.MagicMock()

    stopped = notion_cards.stop_all_running(notion, test_db)

    assert stopped == [tid]
    call = notion.pages.update.call_args
    assert call.kwargs["page_id"] == tid
    props = call.kwargs["properties"]
    assert props["Status"] == {"select": {"name": "Stopped"}}
    assert "start" in props["End Time"]["date"]


def test_start_tracking_sends_properties():
    notion = mock.MagicMock()
    notion.pages.create.return_value = {"id": "p"}

    page_id, now = notion_cards.start_tracking(
        notion, {"NOTION_DB_TIME_TRACKING": "db-abc"}, "task-1", "Grandma Care"
    )

    assert page_id == "p"
    assert now.tzinfo is not None
    call = notion.pages.create.call_args
    assert call.kwargs["parent"] == {"database_id": "db-abc"}
    props = call.kwargs["properties"]
    assert props["Tasks"] == {"relation": [{"id": "task-1"}]}
    assert props["Status"] == {"select": {"name": "Ing"}}
    assert "start" in props["Start Time"]["date"]


# --- recent_titles --------------------------------------------------------------


def test_recent_titles_orders_by_updated_then_created(test_db):
    _insert_task(test_db, "A")
    b = _insert_task(test_db, "B")
    _insert_task(test_db, "C")
    # B was edited most recently.
    test_db.execute(
        "UPDATE tasks SET notion_updated_at = ? WHERE id = ?",
        ("2026-02-01T00:00:00Z", b),
    )
    test_db.commit()

    titles = notion_cards.recent_titles(test_db, 3)
    assert [n for _id, n in titles] == ["B", "A", "C"]


def test_recent_titles_excludes_deleted_and_limits(test_db):
    _insert_task(test_db, "A")
    _insert_task(test_db, "B")
    _insert_task(test_db, "D", deleted=True)
    assert len(notion_cards.recent_titles(test_db, 10)) == 2
    assert len(notion_cards.recent_titles(test_db, 1)) == 1


# --- command wiring -------------------------------------------------------------


def _wire(monkeypatch, test_db, **env):
    """Point the CLI at the test db and stub out Notion + auto-sync; return the env."""
    env = {
        "NOTION_TOKEN": "tok",
        "NOTION_DB_TASKS": "db-tasks",
        "NOTION_DB_TIME_TRACKING": "db-tt",
        **env,
    }
    monkeypatch.setattr(notion_cards, "connect", lambda e: test_db)
    monkeypatch.setattr(notion_cards, "auto_sync", lambda e: None)
    monkeypatch.setattr(notion_cards, "load_env", lambda: env)
    return env


def _args(**kwargs):
    return SimpleNamespace(**kwargs)


def test_cmd_create(test_db, monkeypatch, capsys):
    _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    notion.pages.create.return_value = {"id": "page-1"}
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)
    monkeypatch.setattr(notion_cards.sync, "data_source_id", lambda n, db: "ds")
    monkeypatch.setattr(notion_cards, "validate_selects", lambda n, ds, p: None)

    notion_cards.cmd_create(_args(name="营业执照变更", status="This Week", due=None, project=None, tags=None, priority=None, description=None), _wire(monkeypatch, test_db))

    out = capsys.readouterr().out
    assert "Created task: 营业执照变更" in out
    assert "id=page-1" in out


def test_cmd_create_resolves_project(test_db, monkeypatch, capsys):
    pid = _insert_project(test_db, "Life")
    _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    notion.pages.create.return_value = {"id": "page-1"}
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)
    monkeypatch.setattr(notion_cards.sync, "data_source_id", lambda n, db: "ds")
    monkeypatch.setattr(notion_cards, "validate_selects", lambda n, ds, p: None)

    notion_cards.cmd_create(_args(name="Task", status=None, due=None, project="Life", tags=None, priority=None, description=None), _wire(monkeypatch, test_db))

    props = notion.pages.create.call_args.kwargs["properties"]
    assert props["Projects"] == {"relation": [{"id": pid}]}


def test_cmd_modify_sends_only_touched_fields(test_db, monkeypatch, capsys):
    tid = _insert_task(test_db, "Grandma Care")
    env = _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)
    monkeypatch.setattr(notion_cards.sync, "data_source_id", lambda n, db: "ds")
    monkeypatch.setattr(notion_cards, "validate_selects", lambda n, ds, p: None)

    notion_cards.cmd_modify(_args(task="Grandma Care", name=None, status="Today", due=None, project=None, tags=None, priority=None, description=None), env)

    props = notion.pages.update.call_args.kwargs["properties"]
    assert set(props) == {"Status"}
    assert props["Status"] == {"select": {"name": "Today"}}
    out = capsys.readouterr().out
    assert "Modified task: Grandma Care" in out
    assert tid in out


def test_cmd_modify_cleared_field_clears(test_db, monkeypatch):
    _insert_task(test_db, "Grandma Care")
    env = _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)
    monkeypatch.setattr(notion_cards.sync, "data_source_id", lambda n, db: "ds")
    monkeypatch.setattr(notion_cards, "validate_selects", lambda n, ds, p: None)

    notion_cards.cmd_modify(_args(task="Grandma Care", name=None, status="", due=None, project=None, tags=None, priority=None, description=None), env)

    props = notion.pages.update.call_args.kwargs["properties"]
    assert props["Status"] == {"select": None}


def test_cmd_modify_no_fields_exits(test_db, monkeypatch):
    _insert_task(test_db, "Grandma Care")
    env = _wire(monkeypatch, test_db)
    with pytest.raises(SystemExit):
        notion_cards.cmd_modify(_args(task="Grandma Care", name=None, status=None, due=None, project=None, tags=None, priority=None, description=None), env)


def test_cmd_delete_archives(test_db, monkeypatch, capsys):
    tid = _insert_task(test_db, "Grandma Care")
    env = _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)

    notion_cards.cmd_delete(_args(task="Grandma Care"), env)

    notion.pages.update.assert_called_once_with(page_id=tid, archived=True)
    assert "Archived task: Grandma Care" in capsys.readouterr().out


def test_cmd_start_stops_then_starts(test_db, monkeypatch, capsys):
    tid = _insert_task(test_db, "Grandma Care")
    _insert_open_tracker(test_db, tid)
    env = _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    notion.pages.create.return_value = {"id": "page-9"}
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)

    notion_cards.cmd_start(_args(task="Grandma Care"), env)

    out = capsys.readouterr().out
    assert "Starting tracker for: Grandma Care" in out
    assert "Started at" in out
    assert "stopped 1 previously open tracker(s)" in out
    # The previously open tracker was stopped, and a new one created.
    notion.pages.update.assert_called_once()
    notion.pages.create.assert_called_once()


def test_cmd_end_no_open_trackers(test_db, monkeypatch, capsys):
    env = _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)

    notion_cards.cmd_end(_args(), env)

    assert "No open time trackers to stop." in capsys.readouterr().out
    notion.pages.update.assert_not_called()


def test_cmd_end_stops_all(test_db, monkeypatch, capsys):
    task = _insert_task(test_db, "Grandma Care")
    _insert_open_tracker(test_db, task)
    env = _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)

    notion_cards.cmd_end(_args(), env)

    assert "Stopped 1 tracker(s)" in capsys.readouterr().out


def test_cmd_recent_uses_env_limit(test_db, monkeypatch, capsys):
    _insert_task(test_db, "A")
    _insert_task(test_db, "B")
    monkeypatch.setattr(notion_cards, "connect", lambda env: test_db)

    notion_cards.cmd_recent(_args(limit=None), {"RECENT_CARDS_LIMIT": "1"})

    out = capsys.readouterr().out
    assert len([line for line in out.splitlines() if line.strip()]) == 1


def test_cmd_frequent_lists_ids_with_default_limit(test_db, monkeypatch, capsys):
    for i in range(20):
        _insert_task(test_db, f"Task {i}")
    _insert_project(test_db, "Life")
    _insert_project(test_db, "Work", deleted=True)
    monkeypatch.setattr(notion_cards, "connect", lambda env: test_db)

    notion_cards.cmd_frequent(_args(limit=15), {})

    out = capsys.readouterr().out
    assert "Tasks (top 15 by recent use):" in out
    assert "Projects (top 15 by recent use):" in out
    assert "Work" not in out   # deleted projects excluded
    task_rows = [line for line in out.splitlines() if "Task " in line]
    assert len(task_rows) == 15
    assert "Life" in out


def _comment(cid="c-1", text="hello"):
    return {"id": cid, "created_time": "2026-01-02T10:00:00.000Z",
            "created_by": [{"name": "Bot"}], "rich_text": [{"plain_text": text}]}


def test_comment_read(test_db, monkeypatch, capsys):
    _insert_task(test_db, "Grandma Care")
    _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    notion.comments.list.return_value = {"results": [_comment(text="first"), _comment("c-2", "second")]}
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)

    notion_cards.cmd_comment(_args(card="Grandma Care", action="read", text=None, comment_id=None), {"NOTION_TOKEN": "tok"})

    out = capsys.readouterr().out
    assert "first" in out and "second" in out and "c-2" in out


def test_comment_create(test_db, monkeypatch, capsys):
    _insert_task(test_db, "Grandma Care")
    _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    notion.comments.create.return_value = {"id": "c-new"}
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)

    notion_cards.cmd_comment(_args(card="Grandma Care", action="create", text="done", comment_id=None), {"NOTION_TOKEN": "tok"})

    call = notion.comments.create.call_args
    assert call.kwargs["parent"] == {"page_id": call.kwargs["parent"]["page_id"]}
    assert call.kwargs["rich_text"] == [{"type": "text", "text": {"content": "done"}}]


def test_comment_update_defaults_to_latest(test_db, monkeypatch, capsys):
    _insert_task(test_db, "Grandma Care")
    _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    notion.comments.list.return_value = {"results": [_comment("c-1"), _comment("c-2")]}
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)

    notion_cards.cmd_comment(_args(card="Grandma Care", action="update", text="changed", comment_id=None), {"NOTION_TOKEN": "tok"})

    assert notion.comments.update.call_args.kwargs["comment_id"] == "c-2"


def test_comment_delete_explicit_id(test_db, monkeypatch, capsys):
    _insert_task(test_db, "Grandma Care")
    _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)

    notion_cards.cmd_comment(_args(card="Grandma Care", action="delete", text=None, comment_id="c-9"), {"NOTION_TOKEN": "tok"})

    notion.comments.delete.assert_called_once_with(comment_id="c-9")


def test_comment_create_requires_text(test_db, monkeypatch):
    _insert_task(test_db, "Grandma Care")
    _wire(monkeypatch, test_db)
    monkeypatch.setattr(notion_cards, "Client", lambda **k: mock.MagicMock())

    with pytest.raises(SystemExit):
        notion_cards.cmd_comment(_args(card="Grandma Care", action="create", text=None, comment_id=None), {"NOTION_TOKEN": "tok"})


def test_comment_fails_when_no_comments(test_db, monkeypatch):
    _insert_task(test_db, "Grandma Care")
    _wire(monkeypatch, test_db)
    notion = mock.MagicMock()
    notion.comments.list.return_value = {"results": []}
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)

    with pytest.raises(SystemExit):
        notion_cards.cmd_comment(_args(card="Grandma Care", action="delete", text=None, comment_id=None), {"NOTION_TOKEN": "tok"})


def test_cmd_frequent_respects_limit(test_db, monkeypatch, capsys):
    for i in range(5):
        _insert_task(test_db, f"Task {i}")
    _insert_project(test_db, "Life")
    monkeypatch.setattr(notion_cards, "connect", lambda env: test_db)

    notion_cards.cmd_frequent(_args(limit=2), {})

    out = capsys.readouterr().out
    assert "top 2 by recent use" in out
    task_rows = [line for line in out.splitlines() if "Task " in line]
    assert len(task_rows) == 2


def test_cmd_sync_initializes_and_syncs(test_db, monkeypatch, capsys):
    env = _wire(
        monkeypatch,
        test_db,
        NOTION_DB_PROJECTS="p",
        NOTION_DB_RECORDS="r",
    )
    notion = mock.MagicMock()
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)
    sync_all = mock.Mock()
    monkeypatch.setattr(notion_cards.sync, "sync_all", sync_all)
    init_schema = mock.Mock()
    monkeypatch.setattr(notion_cards.sync, "init_schema", init_schema)

    notion_cards.cmd_sync(_args(full=False), env)

    init_schema.assert_called_once()
    assert sync_all.call_args.kwargs["full"] is False


def test_auto_sync_refreshes_mirror(test_db, monkeypatch, capsys):
    env = {"NOTION_TOKEN": "tok", "NOTION_DB_PROJECTS": "p", "NOTION_DB_RECORDS": "r",
           "NOTION_DB_TASKS": "t", "NOTION_DB_TIME_TRACKING": "tt"}
    monkeypatch.setattr(notion_cards, "connect", lambda e: test_db)
    notion = mock.MagicMock()
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)
    monkeypatch.setattr(notion_cards.sync, "sync_all", lambda c, e, conn, full=False: None)

    notion_cards.auto_sync(env)

    assert "Mirror synced." in capsys.readouterr().out
    notion.close.assert_called_once()


def test_main_happy_end(monkeypatch, test_db, capsys):
    monkeypatch.setattr(sys, "argv", ["notion_cards.py", "end"])
    monkeypatch.setattr(
        notion_cards,
        "load_env",
        lambda: {"NOTION_TOKEN": "tok", "NOTION_DB_PROJECTS": "p", "NOTION_DB_RECORDS": "r",
                 "NOTION_DB_TASKS": "t", "NOTION_DB_TIME_TRACKING": "tt"},
    )
    monkeypatch.setattr(notion_cards, "connect", lambda env: test_db)
    notion = mock.MagicMock()
    monkeypatch.setattr(notion_cards, "Client", lambda **k: notion)
    monkeypatch.setattr(notion_cards, "auto_sync", lambda env: None)

    notion_cards.main()  # end with no open trackers -> no-op, no crash

    assert "No open time trackers to stop." in capsys.readouterr().out


def test_main_schema_mismatch_exits(monkeypatch, test_db):
    monkeypatch.setattr(sys, "argv", ["notion_cards.py", "sync"])
    monkeypatch.setattr(
        notion_cards,
        "load_env",
        lambda: {
            "NOTION_TOKEN": "tok",
            "NOTION_DB_PROJECTS": "p",
            "NOTION_DB_RECORDS": "r",
            "NOTION_DB_TASKS": "t",
            "NOTION_DB_TIME_TRACKING": "tt",
        },
    )
    monkeypatch.setattr(notion_cards, "connect", lambda env: test_db)
    monkeypatch.setattr(notion_cards, "Client", lambda **k: mock.MagicMock())

    def boom(client, env, conn, full=False):
        raise notion_cards.sync.SchemaMismatchError("tasks", ["x"])

    monkeypatch.setattr(notion_cards.sync, "sync_all", boom)
    with pytest.raises(SystemExit):
        notion_cards.main()
