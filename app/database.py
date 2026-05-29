"""SQLite persistence layer: connection pool, pragmas, and schema initialization."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any, Generator

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_PATH = "/app/data/weather.db"
DEFAULT_POOL_SIZE = 5

INIT_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS weather_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        city TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        temperature_2m REAL NOT NULL,
        apparent_temperature REAL NOT NULL,
        precipitation REAL NOT NULL,
        wind_speed_10m REAL NOT NULL,
        weather_code INTEGER NOT NULL,
        UNIQUE(city, timestamp)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS notable_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        city TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        rationale TEXT NOT NULL,
        payload_snapshot TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS polling_metrics (
        hour_bucket TEXT NOT NULL PRIMARY KEY,
        total_polls INTEGER DEFAULT 0,
        failed_polls INTEGER DEFAULT 0
    );
    """,
)

PRAGMA_STATEMENTS = (
    "PRAGMA journal_mode = WAL;",
    "PRAGMA synchronous = NORMAL;",
    "PRAGMA foreign_keys = ON;",
)


def resolve_database_path() -> str:
    return os.environ.get("DATABASE_PATH", DEFAULT_DATABASE_PATH)


def hour_bucket_from_timestamp(timestamp: str) -> str:
    normalized = timestamp.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    truncated = parsed.astimezone(timezone.utc).replace(
        minute=0, second=0, microsecond=0
    )
    return truncated.strftime("%Y-%m-%dT%H:00")


class DatabasePool:
    """Thread-safe SQLite connection pool with startup schema initialization."""

    def __init__(self, database_path: str, pool_size: int = DEFAULT_POOL_SIZE) -> None:
        self._database_path = database_path
        self._pool_size = pool_size
        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._closed = False
        self._initialize_filesystem()
        self._bootstrap_schema()
        self._fill_pool()

    def _initialize_filesystem(self) -> None:
        parent = Path(self._database_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    def _create_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._database_path,
            check_same_thread=False,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        for pragma in PRAGMA_STATEMENTS:
            connection.execute(pragma)
        return connection

    def _bootstrap_schema(self) -> None:
        connection = self._create_connection()
        try:
            connection.execute("BEGIN IMMEDIATE;")
            for statement in INIT_SCHEMA_SQL:
                connection.execute(statement)
            connection.execute("COMMIT;")
            logger.info(
                "Database schema initialized at path: %s",
                self._database_path,
            )
        except sqlite3.Error:
            connection.execute("ROLLBACK;")
            logger.exception("Failed to initialize database schema")
            raise
        finally:
            connection.close()

    def _fill_pool(self) -> None:
        for _ in range(self._pool_size):
            self._pool.put(self._create_connection())

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        if self._closed:
            raise RuntimeError("Database pool is closed")
        pooled: sqlite3.Connection | None = None
        try:
            pooled = self._pool.get(timeout=30)
            yield pooled
        except Empty as exc:
            raise TimeoutError("Timed out waiting for database connection") from exc
        finally:
            if pooled is not None and not self._closed:
                try:
                    self._pool.put_nowait(pooled)
                except Full:
                    pooled.close()

    def close_all(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            while True:
                try:
                    connection = self._pool.get_nowait()
                except Empty:
                    break
                connection.close()
            logger.info("Database connection pool closed")


_pool: DatabasePool | None = None
_pool_lock = threading.Lock()


def get_pool() -> DatabasePool:
    global _pool
    with _pool_lock:
        if _pool is None:
            path = resolve_database_path()
            size_raw = os.environ.get("DATABASE_POOL_SIZE", str(DEFAULT_POOL_SIZE))
            try:
                pool_size = int(size_raw)
            except ValueError as exc:
                raise ValueError("DATABASE_POOL_SIZE must be an integer") from exc
            if pool_size < 1:
                raise ValueError("DATABASE_POOL_SIZE must be at least 1")
            _pool = DatabasePool(path, pool_size=pool_size)
        return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close_all()
            _pool = None


def get_latest_timestamp(pool: DatabasePool, city: str) -> str | None:
    with pool.connection() as connection:
        cursor = connection.execute(
            """
            SELECT timestamp FROM weather_readings
            WHERE city = ?
            ORDER BY timestamp DESC
            LIMIT 1;
            """,
            (city,),
        )
        row = cursor.fetchone()
        return row["timestamp"] if row else None


def insert_reading(
    pool: DatabasePool,
    city: str,
    timestamp: str,
    temperature_2m: float,
    apparent_temperature: float,
    precipitation: float,
    wind_speed_10m: float,
    weather_code: int,
) -> int:
    with pool.connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE;")
            cursor = connection.execute(
                """
                INSERT INTO weather_readings (
                    city,
                    timestamp,
                    temperature_2m,
                    apparent_temperature,
                    precipitation,
                    wind_speed_10m,
                    weather_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    city,
                    timestamp,
                    temperature_2m,
                    apparent_temperature,
                    precipitation,
                    wind_speed_10m,
                    weather_code,
                ),
            )
            connection.execute("COMMIT;")
            return int(cursor.lastrowid)
        except sqlite3.Error:
            connection.execute("ROLLBACK;")
            raise


def insert_event(
    pool: DatabasePool,
    city: str,
    timestamp: str,
    event_type: str,
    rationale: str,
    payload_snapshot: dict[str, Any],
) -> int:
    snapshot_json = json.dumps(payload_snapshot, separators=(",", ":"))
    with pool.connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE;")
            cursor = connection.execute(
                """
                INSERT INTO notable_events (
                    city,
                    timestamp,
                    event_type,
                    rationale,
                    payload_snapshot
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (city, timestamp, event_type, rationale, snapshot_json),
            )
            connection.execute("COMMIT;")
            return int(cursor.lastrowid)
        except sqlite3.Error:
            connection.execute("ROLLBACK;")
            raise


def record_poll_cycle(pool: DatabasePool, timestamp: str, failed: bool) -> None:
    bucket = hour_bucket_from_timestamp(timestamp)
    failed_increment = 1 if failed else 0
    with pool.connection() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE;")
            connection.execute(
                """
                INSERT INTO polling_metrics (hour_bucket, total_polls, failed_polls)
                VALUES (?, 1, ?)
                ON CONFLICT(hour_bucket) DO UPDATE SET
                    total_polls = total_polls + 1,
                    failed_polls = failed_polls + ?;
                """,
                (bucket, failed_increment, failed_increment),
            )
            connection.execute("COMMIT;")
        except sqlite3.Error:
            connection.execute("ROLLBACK;")
            raise


def rollback_idle_transaction(pool: DatabasePool) -> None:
    with pool.connection() as connection:
        connection.execute("ROLLBACK;")


def get_readings(
    pool: DatabasePool,
    city: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 1000))
    if city:
        query = """
            SELECT
                id,
                city,
                timestamp,
                temperature_2m,
                apparent_temperature,
                precipitation,
                wind_speed_10m,
                weather_code
            FROM weather_readings
            WHERE city = ?
            ORDER BY timestamp DESC
            LIMIT ?;
        """
        params: tuple[Any, ...] = (city, bounded_limit)
    else:
        query = """
            SELECT
                id,
                city,
                timestamp,
                temperature_2m,
                apparent_temperature,
                precipitation,
                wind_speed_10m,
                weather_code
            FROM weather_readings
            ORDER BY timestamp DESC
            LIMIT ?;
        """
        params = (bounded_limit,)

    with pool.connection() as connection:
        cursor = connection.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_events(
    pool: DatabasePool,
    city: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 1000))
    if city:
        query = """
            SELECT
                id,
                city,
                timestamp,
                event_type,
                rationale,
                payload_snapshot
            FROM notable_events
            WHERE city = ?
            ORDER BY timestamp DESC
            LIMIT ?;
        """
        params: tuple[Any, ...] = (city, bounded_limit)
    else:
        query = """
            SELECT
                id,
                city,
                timestamp,
                event_type,
                rationale,
                payload_snapshot
            FROM notable_events
            ORDER BY timestamp DESC
            LIMIT ?;
        """
        params = (bounded_limit,)

    with pool.connection() as connection:
        cursor = connection.execute(query, params)
        rows: list[dict[str, Any]] = []
        for row in cursor.fetchall():
            item = dict(row)
            item["payload_snapshot"] = json.loads(item["payload_snapshot"])
            rows.append(item)
        return rows


def get_health_snapshot(pool: DatabasePool) -> dict[str, Any]:
    with pool.connection() as connection:
        readings_count = connection.execute(
            "SELECT COUNT(*) AS count FROM weather_readings;"
        ).fetchone()["count"]
        events_count = connection.execute(
            "SELECT COUNT(*) AS count FROM notable_events;"
        ).fetchone()["count"]
        metrics_rows = connection.execute(
            """
            SELECT hour_bucket, total_polls, failed_polls
            FROM polling_metrics
            ORDER BY hour_bucket DESC
            LIMIT 24;
            """
        ).fetchall()
        latest_reading = connection.execute(
            """
            SELECT city, timestamp
            FROM weather_readings
            ORDER BY timestamp DESC
            LIMIT 1;
            """
        ).fetchone()

    metrics = [
        {
            "hour_bucket": row["hour_bucket"],
            "total_polls": row["total_polls"],
            "failed_polls": row["failed_polls"],
        }
        for row in metrics_rows
    ]

    snapshot: dict[str, Any] = {
        "status": "healthy",
        "readings_count": readings_count,
        "events_count": events_count,
        "polling_metrics_recent": metrics,
    }
    if latest_reading:
        snapshot["latest_reading"] = {
            "city": latest_reading["city"],
            "timestamp": latest_reading["timestamp"],
        }
    return snapshot
