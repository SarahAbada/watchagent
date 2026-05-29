"""Asymmetric event detection engine rubric tests."""

from __future__ import annotations

from app import database
from app.engine import WeatherEvaluationEngine


def _reading(
  city: str,
  timestamp: str,
  temperature_2m: float,
  apparent_temperature: float,
  precipitation: float,
  wind_speed_10m: float,
  weather_code: int = 0,
) -> dict[str, object]:
  return {
    "city": city,
    "timestamp": timestamp,
    "temperature_2m": temperature_2m,
    "apparent_temperature": apparent_temperature,
    "precipitation": precipitation,
    "wind_speed_10m": wind_speed_10m,
    "weather_code": weather_code,
  }


def _event_types(events: list[dict[str, object]]) -> set[str]:
  return {str(event["event_type"]) for event in events}


def test_vancouver_scs_at_minus_six_ottawa_does_not_trigger(
  isolated_db: tuple[str, database.DatabasePool],
) -> None:
  _, pool = isolated_db
  engine = WeatherEvaluationEngine(pool)

  vancouver_reading = _reading(
    city="Vancouver",
    timestamp="2026-05-28T12:00",
    temperature_2m=-6.0,
    apparent_temperature=-8.0,
    precipitation=0.0,
    wind_speed_10m=12.0,
  )
  ottawa_reading = _reading(
    city="Ottawa",
    timestamp="2026-05-28T12:00",
    temperature_2m=-6.0,
    apparent_temperature=-8.0,
    precipitation=0.0,
    wind_speed_10m=12.0,
  )

  vancouver_events = engine.evaluate_reading(vancouver_reading)
  ottawa_events = engine.evaluate_reading(ottawa_reading)

  vancouver_scs = [
    event
    for event in vancouver_events
    if event["event_type"] == "SCS" and event["city"] == "Vancouver"
  ]
  ottawa_scs = [event for event in ottawa_events if event["event_type"] == "SCS"]

  assert len(vancouver_scs) == 1
  assert "pipe bursts" in vancouver_scs[0]["rationale"]
  assert len(ottawa_scs) == 0


def test_toronto_severe_flood_risk_at_twenty_six_mm_includes_dvp_rationale(
  isolated_db: tuple[str, database.DatabasePool],
) -> None:
  _, pool = isolated_db
  engine = WeatherEvaluationEngine(pool)

  toronto_reading = _reading(
    city="Toronto",
    timestamp="2026-05-28T13:00",
    temperature_2m=18.0,
    apparent_temperature=16.0,
    precipitation=26.0,
    wind_speed_10m=20.0,
  )

  events = engine.evaluate_reading(toronto_reading)
  severe_floods = [event for event in events if event["event_type"] == "SFR"]

  assert len(severe_floods) == 1
  assert severe_floods[0]["city"] == "Toronto"
  assert "Don Valley Parkway" in severe_floods[0]["rationale"]
  assert "26.0mm" in severe_floods[0]["rationale"]


def test_windsor_upstream_surge_triggers_corridor_warning(
  isolated_db: tuple[str, database.DatabasePool],
) -> None:
  _, pool = isolated_db
  engine = WeatherEvaluationEngine(pool)

  database.insert_reading(
    pool,
    city="Toronto",
    timestamp="2026-05-28T14:00",
    temperature_2m=8.0,
    apparent_temperature=6.0,
    precipitation=0.5,
    wind_speed_10m=12.0,
    weather_code=3,
  )
  database.insert_reading(
    pool,
    city="Windsor",
    timestamp="2026-05-28T13:00",
    temperature_2m=10.0,
    apparent_temperature=8.0,
    precipitation=0.0,
    wind_speed_10m=15.0,
    weather_code=3,
  )

  windsor_surge = _reading(
    city="Windsor",
    timestamp="2026-05-28T14:00",
    temperature_2m=2.0,
    apparent_temperature=0.0,
    precipitation=12.0,
    wind_speed_10m=25.0,
    weather_code=65,
  )

  events = engine.evaluate_reading(windsor_surge)
  corridor_events = [
    event for event in events if event["event_type"] == "CORRIDOR_WARNING"
  ]

  assert len(corridor_events) == 1
  assert corridor_events[0]["city"] == "Toronto"
  assert "CORRIDOR_WARNING" in corridor_events[0]["rationale"]
  assert "Station: Windsor" in corridor_events[0]["rationale"]


def test_normal_readings_do_not_fire_events(
  isolated_db: tuple[str, database.DatabasePool],
) -> None:
  _, pool = isolated_db
  engine = WeatherEvaluationEngine(pool)

  normal_samples = [
    _reading(
      city="Toronto",
      timestamp="2026-05-28T15:00",
      temperature_2m=18.0,
      apparent_temperature=16.0,
      precipitation=2.0,
      wind_speed_10m=12.0,
    ),
    _reading(
      city="Ottawa",
      timestamp="2026-05-28T15:00",
      temperature_2m=10.0,
      apparent_temperature=8.0,
      precipitation=1.0,
      wind_speed_10m=10.0,
    ),
    _reading(
      city="Vancouver",
      timestamp="2026-05-28T15:00",
      temperature_2m=12.0,
      apparent_temperature=10.0,
      precipitation=3.0,
      wind_speed_10m=15.0,
    ),
  ]

  for sample in normal_samples:
    events = engine.evaluate_reading(sample)
    assert events == [], f"Expected no events for {sample['city']}, got {events}"


def test_moderate_flood_not_fired_when_below_city_threshold(
  isolated_db: tuple[str, database.DatabasePool],
) -> None:
  _, pool = isolated_db
  engine = WeatherEvaluationEngine(pool)

  toronto_reading = _reading(
    city="Toronto",
    timestamp="2026-05-28T16:00",
    temperature_2m=20.0,
    apparent_temperature=18.0,
    precipitation=10.0,
    wind_speed_10m=10.0,
  )

  events = engine.evaluate_reading(toronto_reading)
  assert "MFR" not in _event_types(events)
  assert "SFR" not in _event_types(events)
