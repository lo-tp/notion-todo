"""Unit tests for scripts/create_databases.py."""

from unittest import mock

import httpx
import pytest

import create_databases

# --- normalize_page_id -----------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("3e5db18bdc5f808c9f6ae60a6cb8f95f", "3e5db18bdc5f808c9f6ae60a6cb8f95f"),
        ("3e5db18b-dc5f-808c-9f6a-e60a6cb8f95f", "3e5db18bdc5f808c9f6ae60a6cb8f95f"),
        (
            "https://www.notion.so/My-Workspace/3e5db18bdc5f808c9f6ae60a6cb8f95f",
            "3e5db18bdc5f808c9f6ae60a6cb8f95f",
        ),
        (
            "https://www.notion.so/p/3e5db18b-dc5f-808c-9f6a-e60a6cb8f95f",
            "3e5db18bdc5f808c9f6ae60a6cb8f95f",
        ),
        (
            "https://www.notion.so/p/3e5db18bdc5f808c9f6ae60a6cb8f95f?v=abc",
            "3e5db18bdc5f808c9f6ae60a6cb8f95f",
        ),
        ("  3e5db18bdc5f808c9f6ae60a6cb8f95f  ", "3e5db18bdc5f808c9f6ae60a6cb8f95f"),
    ],
)
def test_normalize_page_id(value, expected):
    assert create_databases.normalize_page_id(value) == expected


# --- load_env / write_env_keys ---------------------------------------------


def test_load_env(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("A=1\n# a comment\nB=two\n\n")
    monkeypatch.setattr(create_databases, "ENV_PATH", p)
    assert create_databases.load_env() == {"A": "1", "B": "two"}


def test_write_env_keys_insert_and_replace(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("NOTION_TOKEN=abc\n# keep me\nNOTION_DB_TASKS=old\n")
    monkeypatch.setattr(create_databases, "ENV_PATH", p)

    create_databases.write_env_keys({"NOTION_DB_TASKS": "new", "NOTION_DB_PROJECTS": "proj"})

    lines = p.read_text().splitlines()
    assert "NOTION_DB_TASKS=new" in lines
    assert "NOTION_DB_PROJECTS=proj" in lines
    assert "NOTION_TOKEN=abc" in lines
    assert "# keep me" in lines
    assert "NOTION_DB_TASKS=old" not in lines


# --- provision (mocked Notion client) --------------------------------------


def _mock_notion(monkeypatch):
    notion = mock.MagicMock()
    notion.pages.retrieve.return_value = {"archived": False}
    # No pre-existing children under the parent.
    monkeypatch.setattr(
        create_databases,
        "collect_paginated_api",
        lambda *a, **k: [],
    )

    counter = iter(range(1000))

    def _create(*a, **k):
        did = f"db-{next(counter)}"
        return {"id": did}

    def _retrieve(*a, **k):
        return {"data_sources": [{"id": "ds-" + k["database_id"]}], "title": []}

    notion.databases.create.side_effect = _create
    notion.databases.retrieve.side_effect = _retrieve
    return notion


def test_provision_creates_four_databases(monkeypatch):
    notion = _mock_notion(monkeypatch)

    ids = create_databases.provision(notion, "parent123")

    assert notion.databases.create.call_count == 4
    assert set(ids) == {"projects", "records", "tasks", "time_tracking"}
    assert all(isinstance(v, str) and v for v in ids.values())


def test_provision_wires_relations_and_rollups(monkeypatch):
    notion = _mock_notion(monkeypatch)

    create_databases.provision(notion, "parent123")

    # 3 relation updates + 2 time-tracking (rollup + formulas) + 1 tasks-rollups update
    assert notion.data_sources.update.call_count == 6


def test_provision_refuses_existing_tasks(monkeypatch):
    notion = _mock_notion(monkeypatch)
    monkeypatch.setattr(
        create_databases,
        "collect_paginated_api",
        lambda *a, **k: [{"type": "child_database", "id": "db-existing"}],
    )
    # Override the mock's side_effect (side_effect wins over return_value).
    notion.databases.retrieve.side_effect = lambda *a, **k: {"title": [{"plain_text": "Tasks"}]}

    with pytest.raises(SystemExit):
        create_databases.provision(notion, "parent123")
    # Nothing should be created.
    notion.databases.create.assert_not_called()


def test_provision_refuses_archived_parent(monkeypatch):
    notion = mock.MagicMock()
    notion.pages.retrieve.return_value = {"archived": True}
    monkeypatch.setattr(create_databases, "collect_paginated_api", lambda *a, **k: [])

    with pytest.raises(SystemExit):
        create_databases.provision(notion, "parent123")
    notion.databases.create.assert_not_called()


# --- main() ----------------------------------------------------------------


def test_main_happy(monkeypatch):
    monkeypatch.setattr(
        create_databases,
        "load_env",
        lambda: {
            "NOTION_TOKEN": "tok",
            "NOTION_PARENT_PAGE": "3e5db18bdc5f808c9f6ae60a6cb8f95f",
        },
    )
    mock_client = mock.MagicMock()
    monkeypatch.setattr(create_databases, "Client", lambda **k: mock_client)
    monkeypatch.setattr(
        create_databases,
        "provision",
        lambda notion, parent: {
            "projects": "p",
            "records": "r",
            "tasks": "t",
            "time_tracking": "tt",
        },
    )
    written = {}

    def fake_write(updates):
        written.update(updates)

    monkeypatch.setattr(create_databases, "write_env_keys", fake_write)

    create_databases.main()

    mock_client.close.assert_called_once()
    assert written == {
        "NOTION_DB_PROJECTS": "p",
        "NOTION_DB_RECORDS": "r",
        "NOTION_DB_TASKS": "t",
        "NOTION_DB_TIME_TRACKING": "tt",
    }


def test_main_missing_keys_exits(monkeypatch):
    monkeypatch.setattr(create_databases, "load_env", lambda: {"NOTION_TOKEN": "tok"})
    with pytest.raises(SystemExit):
        create_databases.main()


def test_main_api_error_exits(monkeypatch):
    monkeypatch.setattr(
        create_databases,
        "load_env",
        lambda: {
            "NOTION_TOKEN": "tok",
            "NOTION_PARENT_PAGE": "abc",
        },
    )
    mock_client = mock.MagicMock()
    monkeypatch.setattr(create_databases, "Client", lambda **k: mock_client)

    def boom(notion, parent):
        raise create_databases.APIResponseError(
            "bad", 400, "invalid_request", headers=httpx.Headers(), raw_body_text=""
        )

    monkeypatch.setattr(create_databases, "provision", boom)
    monkeypatch.setattr(create_databases, "write_env_keys", lambda updates: None)

    with pytest.raises(SystemExit):
        create_databases.main()
    # The client is always closed in the finally block.
    mock_client.close.assert_called_once()
