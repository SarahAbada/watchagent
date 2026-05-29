"""Shared pytest fixtures for isolated on-disk SQLite databases."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Generator

import pytest

from app import database

PRAGMA_STATEMENTS = (
    "PRAGMA journal_mode = WAL;",
    "PRAGMA synchronous = NORMAL;",
    "PRAGMA foreign_keys = ON;",
)

ALLOWED_TABLES = frozenset(
    {"weather_readings", "notable_events", "polling_metrics"}
)


def purge_database_files(db_path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = f"{db_path}{suffix}"
        try:
            os.remove(candidate)
        except FileNotFoundError:
            continue


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    purge_database_files(path)
    try:
        yield path
    finally:
        database.close_pool()
        purge_database_files(path)


@pytest.fixture
def isolated_db(
    temp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[str, database.DatabasePool], None, None]:
    monkeypatch.setenv("DATABASE_PATH", temp_db_path)
    database.close_pool()
    connection = sqlite3.connect(temp_db_path)
    try:
        for pragma in PRAGMA_STATEMENTS:
            connection.execute(pragma)
    finally:
        connection.close()
    pool = database.get_pool()
    try:
        yield temp_db_path, pool
    finally:
        database.close_pool()
        purge_database_files(temp_db_path)


def count_table_rows(db_path: str, table_name: str) -> int:
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"Unsupported table name: {table_name}")
    connection = sqlite3.connect(db_path)
    try:
        if table_name == "weather_readings":
            query = "SELECT COUNT(*) FROM weather_readings;"
        elif table_name == "notable_events":
            query = "SELECT COUNT(*) FROM notable_events;"
        else:
            query = "SELECT COUNT(*) FROM polling_metrics;"
        cursor = connection.execute(query)
        return int(cursor.fetchone()[0])
    finally:
        connection.close()
