"""Shared pytest fixtures for the notion-sync test suite.

- Puts ``sync/`` and ``scripts/`` on the import path so their modules can be
  imported directly.
- Provides :func:`test_db`, a psycopg connection to an **in-memory** PostgreSQL
  (via ``py-pglite`` — a real Postgres engine, no external server). Tables are
  truncated before each test for isolation.
"""

import sys
from pathlib import Path

import psycopg
import pytest
from py_pglite import PGliteManager

ROOT = Path(__file__).resolve().parent.parent
for _sub in ("sync", "scripts"):
    _p = str(ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

_SCHEMA = (ROOT / "sync" / "schema.sql").read_text()
_TABLES = "projects, tasks, records, time_tracking, sync_state"


@pytest.fixture(scope="session")
def pglite_db():
    """Start one in-memory Postgres (PGlite) for the whole test session and
    yield a single psycopg connection with the project schema applied."""
    with PGliteManager() as manager:
        conn = psycopg.connect(manager.get_dsn())
        conn.execute(_SCHEMA.encode())
        conn.commit()
        yield conn
        conn.close()


@pytest.fixture
def test_db(pglite_db):
    """Yield the shared connection with all mirror tables emptied, so each test
    starts from a clean slate."""
    pglite_db.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY;")
    pglite_db.commit()
    yield pglite_db
