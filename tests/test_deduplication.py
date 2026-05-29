"""Deduplication and immutability contract tests."""

from __future__ import annotations

import inspect
from unittest.mock import patch

from app import database
from app.poller import WeatherPoller
from tests.conftest import count_table_rows


def _toronto_payload(timestamp: str = "2026-05-28T15:00") -> dict[str, object]:
  return {
    "city": "Toronto",
    "timestamp": timestamp,
    "temperature_2m": 14.0,
    "apparent_temperature": 12.0,
    "precipitation": 1.0,
    "wind_speed_10m": 18.0,
    "weather_code": 3,
  }


@patch.object(WeatherPoller, "_persist_events")
@patch.object(WeatherPoller, "_fetch_current")
def test_duplicate_timestamp_commits_single_reading(
  mock_fetch_current: object,
  mock_persist_events: object,
  isolated_db: tuple[str, database.DatabasePool],
) -> None:
  db_path, pool = isolated_db
  payload = _toronto_payload()
  mock_fetch_current.return_value = payload

  poller = WeatherPoller(pool, poll_interval_seconds=300)
  poller._persist_reading("Toronto", dict(payload))
  poller._persist_reading("Toronto", dict(payload))

  assert count_table_rows(db_path, "weather_readings") == 1
  mock_fetch_current.assert_not_called()
  mock_persist_events.assert_called_once()


@patch.object(WeatherPoller, "_persist_events")
@patch.object(WeatherPoller, "_fetch_current")
def test_sequential_poll_with_identical_api_payload_keeps_one_row(
  mock_fetch_current: object,
  mock_persist_events: object,
  isolated_db: tuple[str, database.DatabasePool],
) -> None:
  db_path, pool = isolated_db
  payload = _toronto_payload()
  mock_fetch_current.return_value = payload

  poller = WeatherPoller(pool, poll_interval_seconds=300)

  with patch.object(poller, "_shutdown_event") as mock_shutdown:
    mock_shutdown.is_set.return_value = False
    mock_shutdown.wait.return_value = False
    poller._poll_city("Toronto")
    poller._poll_city("Toronto")

  assert count_table_rows(db_path, "weather_readings") == 1
  assert mock_fetch_current.call_count == 2


def test_repository_surface_has_no_update_or_delete_mutators() -> None:
  public_names = {
    name
    for name in dir(database)
    if not name.startswith("_") and callable(getattr(database, name))
  }
  forbidden = {
    name
    for name in public_names
    if "update" in name.lower() or "delete" in name.lower()
  }
  assert forbidden == set()


def test_core_tables_have_no_update_or_delete_sql_in_repository() -> None:
    source = inspect.getsource(database)
    lowered = source.lower()
    for table in ("weather_readings", "notable_events"):
        assert f"update {table}" not in lowered
        assert f"delete from {table}" not in lowered
