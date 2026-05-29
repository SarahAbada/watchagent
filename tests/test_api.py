"""Flask API contract and query behavior tests."""

from __future__ import annotations

import json

import pytest

from app import database
from app.main import app


@pytest.fixture
def api_client(isolated_db: tuple[str, database.DatabasePool]) -> object:
  _db_path, _closed_pool = isolated_db
  database.close_pool()
  pool = database.get_pool()
  app.config["TESTING"] = True
  with app.test_client() as client:
    yield client, pool


def _seed_readings(pool: database.DatabasePool) -> None:
  database.insert_reading(
    pool,
    city="Ottawa",
    timestamp="2026-05-28T10:00",
    temperature_2m=5.0,
    apparent_temperature=3.0,
    precipitation=0.0,
    wind_speed_10m=10.0,
    weather_code=0,
  )
  database.insert_reading(
    pool,
    city="Toronto",
    timestamp="2026-05-28T12:00",
    temperature_2m=12.0,
    apparent_temperature=10.0,
    precipitation=1.0,
    wind_speed_10m=15.0,
    weather_code=3,
  )
  database.insert_reading(
    pool,
    city="Vancouver",
    timestamp="2026-05-28T14:00",
    temperature_2m=18.0,
    apparent_temperature=16.0,
    precipitation=2.0,
    wind_speed_10m=20.0,
    weather_code=61,
  )


def _seed_events(pool: database.DatabasePool) -> None:
  database.insert_event(
    pool,
    city="Toronto",
    timestamp="2026-05-28T12:00",
    event_type="SFR",
    rationale=(
      "[SFR] | Delta: 26.0mm | Context: Critical threshold for Don Valley Parkway "
      "(DVP) inundation | Station: Toronto"
    ),
    payload_snapshot={
      "city": "Toronto",
      "timestamp": "2026-05-28T12:00",
      "temperature_2m": 12.0,
      "apparent_temperature": 10.0,
      "precipitation": 26.0,
      "wind_speed_10m": 15.0,
      "weather_code": 3,
    },
  )
  database.insert_event(
    pool,
    city="Ottawa",
    timestamp="2026-05-28T10:00",
    event_type="SCS",
    rationale=(
      "[SCS] | Delta: -26.0C | Context: Deep continental Arctic freeze; high risk "
      "of residential heating grid overload | Station: Ottawa"
    ),
    payload_snapshot={
      "city": "Ottawa",
      "timestamp": "2026-05-28T10:00",
      "temperature_2m": -26.0,
      "apparent_temperature": -30.0,
      "precipitation": 0.0,
      "wind_speed_10m": 10.0,
      "weather_code": 0,
    },
  )


def test_health_endpoint_contract(api_client: tuple[object, database.DatabasePool]) -> None:
  client, pool = api_client
  _seed_readings(pool)
  _seed_events(pool)

  response = client.get("/health")
  assert response.status_code == 200

  payload = json.loads(response.data)
  assert set(payload.keys()) == {"status", "readings_stored", "events_stored"}
  assert payload["status"] == "ok"
  assert payload["readings_stored"] == 3
  assert payload["events_stored"] == 2

  raw_body = response.data.decode("utf-8")
  assert raw_body.index('"status"') < raw_body.index('"readings_stored"')


def test_readings_endpoint_structure_filter_and_limit(
  api_client: tuple[object, database.DatabasePool],
) -> None:
  client, pool = api_client
  _seed_readings(pool)

  default_response = client.get("/readings")
  assert default_response.status_code == 200
  default_payload = json.loads(default_response.data)
  assert list(default_payload.keys()) == ["readings"]
  assert len(default_payload["readings"]) == 3

  filtered_response = client.get("/readings?city=Ottawa&limit=1")
  assert filtered_response.status_code == 200
  filtered_payload = json.loads(filtered_response.data)
  assert len(filtered_payload["readings"]) == 1
  assert filtered_payload["readings"][0]["city"] == "Ottawa"

  reading_fields = {
    "id",
    "city",
    "timestamp",
    "temperature_2m",
    "apparent_temperature",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
  }
  assert set(filtered_payload["readings"][0].keys()) == reading_fields

  timestamps = [row["timestamp"] for row in default_payload["readings"]]
  assert timestamps == sorted(timestamps, reverse=True)


def test_events_endpoint_structure_filter_and_limit(
  api_client: tuple[object, database.DatabasePool],
) -> None:
  client, pool = api_client
  _seed_events(pool)

  default_response = client.get("/events")
  assert default_response.status_code == 200
  default_payload = json.loads(default_response.data)
  assert list(default_payload.keys()) == ["events"]
  assert len(default_payload["events"]) == 2

  filtered_response = client.get("/events?city=Toronto&limit=1")
  assert filtered_response.status_code == 200
  filtered_payload = json.loads(filtered_response.data)
  assert len(filtered_payload["events"]) == 1
  assert filtered_payload["events"][0]["city"] == "Toronto"
  assert filtered_payload["events"][0]["event_type"] == "SFR"

  event_fields = {
    "id",
    "city",
    "timestamp",
    "event_type",
    "rationale",
    "payload_snapshot",
  }
  assert set(filtered_payload["events"][0].keys()) == event_fields
  assert isinstance(filtered_payload["events"][0]["payload_snapshot"], dict)

  timestamps = [row["timestamp"] for row in default_payload["events"]]
  assert timestamps == sorted(timestamps, reverse=True)


def test_invalid_limit_returns_bad_request(
  api_client: tuple[object, database.DatabasePool],
) -> None:
  client, _pool = api_client

  readings_response = client.get("/readings?limit=abc")
  assert readings_response.status_code == 400
  readings_payload = json.loads(readings_response.data)
  assert "error" in readings_payload

  events_response = client.get("/events?limit=abc")
  assert events_response.status_code == 400
  events_payload = json.loads(events_response.data)
  assert "error" in events_payload
