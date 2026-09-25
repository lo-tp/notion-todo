"""Unit tests for scripts/create_task.py.

Database-touching helpers run against the shared in-memory Postgres (see the
``test_db`` fixture) by pointing ``psycopg.connect`` at that connection.
Notion calls are exercised by mocking the module-level
:class:`~notion_client.Client`.
"""

import sys
import uuid
from datetime import UTC, datetime
from unittest import mock

import create_task
import pytest


def _ctx(value):
    class _Ctx:
        def __enter__(self):
            return value

        def __exit__(self, *exc):
            return False

    return _Ctx()


def _point_connect_at(test_db, monkeypatch):
    """Make ``create_task.psycopg.connect`` return the shared test connection."""
    monkeypatch.setattr(
        create_task.psycopg, "connect", mock.Mock(side_effect=lambda url: _ctx(test_db))
    )


def _insert_project(test_db, name, deleted=False):
    pid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO projects (id, name, notion_updated_at, deleted_at) "
        "VALUES (%s, %s, now(), %s)",
        (pid, name, datetime.now(UTC) if deleted else None),
    )
    test_db.commit()
    return pid


# --- build_properties ------------------------------------------------------


def test_build_properties_minimal():
    props = create_task.build_properties("Task A")
    assert props == {"Name": {"title": [{"text": {"content": "Task A"}}]}}


def test_build_properties_all_fields():
    props = create_task.build_properties(
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


# --- find_project ----------------------------------------------------------


def test_find_project_exact(test_db, monkeypatch):
    pid = _insert_project(test_db, "Life")
    _point_connect_at(test_db, monkeypatch)
    assert create_task.find_project({"DATABASE_URL": "x"}, "Life") == str(pid)


def test_find_project_by_uuid(test_db, monkeypatch):
    pid = _insert_project(test_db, "Life")
    _point_connect_at(test_db, monkeypatch)
    assert create_task.find_project({"DATABASE_URL": "x"}, str(pid)) == str(pid)


def test_find_project_uuid_not_found_exits(test_db, monkeypatch):
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        create_task.find_project({"DATABASE_URL": "x"}, str(uuid.uuid4()))


def test_find_project_ambiguous_exact_exits(test_db, monkeypatch):
    _insert_project(test_db, "Life")
    _insert_project(test_db, "Life")
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        create_task.find_project({"DATABASE_URL": "x"}, "Life")


def test_find_project_unique_substring(test_db, monkeypatch):
    pid = _insert_project(test_db, "Life")
    _insert_project(test_db, "Next Job")
    _point_connect_at(test_db, monkeypatch)
    assert create_task.find_project({"DATABASE_URL": "x"}, "Life") == str(pid)


def test_find_project_ambiguous_substring_exits(test_db, monkeypatch):
    _insert_project(test_db, "Life")
    _insert_project(test_db, "Life Hacks")
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        create_task.find_project({"DATABASE_URL": "x"}, "if")


def test_find_project_no_match_exits(test_db, monkeypatch):
    _insert_project(test_db, "Life")
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        create_task.find_project({"DATABASE_URL": "x"}, "nonexistent")


def test_find_project_excludes_deleted(test_db, monkeypatch):
    _insert_project(test_db, "Life", deleted=True)
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        create_task.find_project({"DATABASE_URL": "x"}, "Life")


# --- validate_selects / data_source_id / create_task ----------------------


def _mock_notion(options_by_prop):
    client = mock.MagicMock()
    client.data_sources.retrieve.return_value = {
        "properties": {
            prop: {"select": {"options": [{"name": o} for o in opts]}}
            for prop, opts in options_by_prop.items()
        }
    }
    return client


def test_validate_selects_accepts_known(monkeypatch):
    notion = _mock_notion({"Status": ["This Week", "Today"]})
    # Should not raise.
    create_task.validate_selects(
        notion, "ds", {"Status": {"select": {"name": "This Week"}}}
    )


def test_validate_selects_rejects_unknown_status():
    notion = _mock_notion({"Status": ["This Week", "Today"]})
    with pytest.raises(SystemExit):
        create_task.validate_selects(
            notion, "ds", {"Status": {"select": {"name": "Nope"}}}
    )


def test_validate_selects_skips_absent_fields():
    notion = _mock_notion({"Status": ["This Week"], "Priority": ["5"]})
    # No Status/Priority in the payload -> nothing to validate.
    create_task.validate_selects(notion, "ds", {"Name": {"title": []}})


def test_data_source_id_returns_first_ds():
    notion = mock.MagicMock()
    notion.databases.retrieve.return_value = {"data_sources": [{"id": "ds-1"}]}
    assert create_task.data_source_id(notion, "db-1") == "ds-1"


def test_create_task_returns_id_and_parent():
    notion = mock.MagicMock()
    notion.pages.create.return_value = {"id": "page-9"}
    page_id = create_task.create_task(notion, "db-tasks", {"Name": {"title": []}})
    assert page_id == "page-9"
    call = notion.pages.create.call_args
    assert call.kwargs["parent"] == {"database_id": "db-tasks"}


# --- main ------------------------------------------------------------------


def test_main_no_args_exits():
    with pytest.raises(SystemExit):
        create_task.main()


def test_main_missing_env_key_exits(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["create_task.py", "Task"])
    monkeypatch.setattr(create_task, "load_env", lambda: {"NOTION_TOKEN": "tok"})
    with pytest.raises(SystemExit):
        create_task.main()


def test_main_happy(monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["create_task.py", "营业执照变更", "--status", "This Week", "--due", "2026-10-01"]
    )
    monkeypatch.setattr(
        create_task,
        "load_env",
        lambda: {"NOTION_TOKEN": "tok", "NOTION_DB_TASKS": "db-tasks"},
    )
    monkeypatch.setattr(create_task, "Client", lambda **k: mock.MagicMock())
    monkeypatch.setattr(create_task, "data_source_id", lambda notion, db: "ds")
    monkeypatch.setattr(create_task, "validate_selects", lambda notion, ds, props: None)
    monkeypatch.setattr(create_task, "create_task", lambda notion, db, props: "page-1")

    create_task.main()

    out = capsys.readouterr().out
    assert "Created task: 营业执照变更" in out
    assert "id=page-1" in out
    assert "Done." in out


def test_main_resolves_project(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["create_task.py", "Task", "--project", "Life"])
    monkeypatch.setattr(
        create_task, "load_env", lambda: {"NOTION_TOKEN": "tok", "NOTION_DB_TASKS": "db"}
    )
    monkeypatch.setattr(create_task, "find_project", lambda env, q: "proj-1")
    monkeypatch.setattr(create_task, "Client", lambda **k: mock.MagicMock())
    captured = {}

    def _capture(notion, db, props):
        captured["props"] = props
        return "page-1"

    monkeypatch.setattr(create_task, "data_source_id", lambda notion, db: "ds")
    monkeypatch.setattr(create_task, "validate_selects", lambda notion, ds, props: None)
    monkeypatch.setattr(create_task, "create_task", _capture)

    create_task.main()

    assert captured["props"]["Projects"] == {"relation": [{"id": "proj-1"}]}
