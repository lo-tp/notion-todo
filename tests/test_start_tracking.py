"""Unit tests for scripts/start_tracking.py.

Database-touching helpers run against the shared in-memory Postgres (see the
``test_db`` fixture) by pointing ``psycopg.connect`` at that connection.
Notion calls are exercised by mocking the module-level
:class:`~notion_client.Client`.
"""

import sys
import uuid
from datetime import UTC, datetime
from unittest import mock

import pytest
import start_tracking


def _ctx(value):
    class _Ctx:
        def __enter__(self):
            return value

        def __exit__(self, *exc):
            return False

    return _Ctx()


def _point_connect_at(test_db, monkeypatch):
    """Make ``start_tracking.psycopg.connect`` return the shared test connection.

    ``start_tracking.psycopg`` and the top-level ``psycopg`` are the same object,
    so ``monkeypatch`` restores the real ``connect`` after each test.
    """
    monkeypatch.setattr(
        start_tracking.psycopg, "connect", mock.Mock(side_effect=lambda url: _ctx(test_db))
    )


def _insert_task(test_db, name, deleted=False):
    tid = str(uuid.uuid4())
    test_db.execute(
        "INSERT INTO tasks (id, name, notion_updated_at, deleted_at) "
        "VALUES (%s, %s, now(), %s)",
        (tid, name, datetime.now(UTC) if deleted else None),
    )
    test_db.commit()
    return tid


# --- find_task -------------------------------------------------------------


def test_find_task_by_uuid(test_db, monkeypatch):
    tid = _insert_task(test_db, "Grandma Care")
    _point_connect_at(test_db, monkeypatch)
    page_id, name = start_tracking.find_task({"DATABASE_URL": "x"}, tid)
    assert page_id == str(tid)
    assert name == "Grandma Care"


def test_find_task_uuid_not_found_exits(test_db, monkeypatch):
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        start_tracking.find_task({"DATABASE_URL": "x"}, str(uuid.uuid4()))


def test_find_task_exact_name(test_db, monkeypatch):
    tid = _insert_task(test_db, "Grandma Care")
    _point_connect_at(test_db, monkeypatch)
    page_id, name = start_tracking.find_task({"DATABASE_URL": "x"}, "Grandma Care")
    assert page_id == str(tid)
    assert name == "Grandma Care"


def test_find_task_ambiguous_exact_exits(test_db, monkeypatch):
    _insert_task(test_db, "Duplicate")
    _insert_task(test_db, "Duplicate")
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        start_tracking.find_task({"DATABASE_URL": "x"}, "Duplicate")


def test_find_task_unique_substring(test_db, monkeypatch):
    tid = _insert_task(test_db, "Grandma Care")
    _insert_task(test_db, "Other Task")
    _point_connect_at(test_db, monkeypatch)
    page_id, name = start_tracking.find_task({"DATABASE_URL": "x"}, "Grandma")
    assert page_id == str(tid)
    assert name == "Grandma Care"


def test_find_task_ambiguous_substring_exits(test_db, monkeypatch):
    _insert_task(test_db, "Care A")
    _insert_task(test_db, "Care B")
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        start_tracking.find_task({"DATABASE_URL": "x"}, "Care")


def test_find_task_no_match_exits(test_db, monkeypatch):
    _insert_task(test_db, "Something Else")
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        start_tracking.find_task({"DATABASE_URL": "x"}, "nonexistent-zzz")


def test_find_task_excludes_deleted(test_db, monkeypatch):
    _insert_task(test_db, "Deleted Task", deleted=True)
    _point_connect_at(test_db, monkeypatch)
    with pytest.raises(SystemExit):
        start_tracking.find_task({"DATABASE_URL": "x"}, "Deleted")


# --- start_tracking --------------------------------------------------------


def test_start_tracking_returns_page_id_and_time(monkeypatch):
    mock_client = mock.MagicMock()
    mock_client.pages.create.return_value = {"id": "page-123"}
    monkeypatch.setattr(start_tracking, "Client", lambda **k: mock_client)

    page_id, now = start_tracking.start_tracking(
        {"NOTION_TOKEN": "tok", "NOTION_DB_TIME_TRACKING": "db"}, "task-1", "Grandma Care"
    )

    assert page_id == "page-123"
    assert now.tzinfo is not None
    mock_client.close.assert_called_once()


def test_start_tracking_sends_properties(monkeypatch):
    mock_client = mock.MagicMock()
    mock_client.pages.create.return_value = {"id": "p"}
    monkeypatch.setattr(start_tracking, "Client", lambda **k: mock_client)

    start_tracking.start_tracking(
        {"NOTION_TOKEN": "tok", "NOTION_DB_TIME_TRACKING": "db-abc"}, "task-1", "Grandma Care"
    )

    call = mock_client.pages.create.call_args
    assert call.kwargs["parent"] == {"database_id": "db-abc"}
    props = call.kwargs["properties"]
    assert props["Tasks"] == {"relation": [{"id": "task-1"}]}
    assert props["Status"] == {"select": {"name": "Ing"}}
    assert "start" in props["Start Time"]["date"]


# --- main ------------------------------------------------------------------


def test_main_no_args_exits(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["start_tracking.py"])
    with pytest.raises(SystemExit):
        start_tracking.main()


def test_main_missing_env_key_exits(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["start_tracking.py", "Task"])
    monkeypatch.setattr(start_tracking, "load_env", lambda: {"NOTION_TOKEN": "tok"})
    with pytest.raises(SystemExit):
        start_tracking.main()


def test_main_happy(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["start_tracking.py", "Grandma Care"])
    monkeypatch.setattr(
        start_tracking,
        "load_env",
        lambda: {
            "NOTION_TOKEN": "tok",
            "NOTION_DB_TIME_TRACKING": "db",
            "DATABASE_URL": "x",
        },
    )
    monkeypatch.setattr(start_tracking, "find_task", lambda env, q: ("task-1", "Grandma Care"))
    monkeypatch.setattr(start_tracking, "stop_all_running", lambda env: [])
    monkeypatch.setattr(
        start_tracking,
        "start_tracking",
        lambda env, tid, name: ("page-1", datetime.now(UTC)),
    )

    start_tracking.main()

    out = capsys.readouterr().out
    assert "Starting tracker for: Grandma Care" in out
    assert "Started at" in out
    assert "Done." in out


def test_main_reports_stopped(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["start_tracking.py", "Grandma Care"])
    monkeypatch.setattr(
        start_tracking,
        "load_env",
        lambda: {"NOTION_TOKEN": "tok", "NOTION_DB_TIME_TRACKING": "db", "DATABASE_URL": "x"},
    )
    monkeypatch.setattr(start_tracking, "find_task", lambda env, q: ("task-1", "Grandma Care"))
    monkeypatch.setattr(start_tracking, "stop_all_running", lambda env: ["a", "b"])
    monkeypatch.setattr(
        start_tracking,
        "start_tracking",
        lambda env, tid, name: ("page-1", datetime.now(UTC)),
    )

    start_tracking.main()

    assert "stopped 2 previously open tracker(s)" in capsys.readouterr().out
