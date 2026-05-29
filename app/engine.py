"""Synchronous asymmetric weather event evaluation engine."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from app import database

logger = logging.getLogger(__name__)

TARGET_CITIES = frozenset({"Ottawa", "Toronto", "Vancouver"})
UPSTREAM_CITIES = frozenset({"Windsor", "Chicago", "Tofino"})
CORRIDOR_UPSTREAM = frozenset({"Windsor", "Chicago"})
CORRIDOR_TARGETS = frozenset({"Toronto", "Ottawa"})

SCS_THRESHOLDS: dict[str, tuple[float, str]] = {
    "Ottawa": (
        -25.0,
        "Deep continental Arctic freeze; high risk of residential heating grid overload",
    ),
    "Toronto": (
        -18.0,
        "Extreme urban cold; transit rail switch failures & vulnerable population risk",
    ),
    "Vancouver": (
        -5.0,
        "Maritime climate shock; high risk of shallow-buried residential pipe bursts",
    ),
}

EHW_THRESHOLDS: dict[str, tuple[float, str]] = {
    "Toronto": (
        32.0,
        "High concrete urban heat island effect; subway traction power strain",
    ),
    "Ottawa": (
        30.0,
        "Continental humidity spike; agricultural stress and electrical grid load",
    ),
    "Vancouver": (
        28.0,
        "Maritime low tolerance event; extreme risk due to low air-conditioning penetration",
    ),
}

MFR_THRESHOLDS: dict[str, tuple[float, str]] = {
    "Toronto": (
        15.0,
        "Concrete pooling and localized urban drainage backups",
    ),
    "Ottawa": (
        20.0,
        "Overwhelmed municipal sewer infrastructure",
    ),
    "Vancouver": (
        30.0,
        "Pacific surge overtaxing coastal gravity drainage systems",
    ),
}

SFR_THRESHOLDS: dict[str, tuple[float, str]] = {
    "Toronto": (
        25.0,
        "Critical threshold for Don Valley Parkway (DVP) inundation",
    ),
    "Ottawa": (
        35.0,
        "Stalled thunderstorm cells along the valley floor",
    ),
    "Vancouver": (
        50.0,
        "Severe atmospheric river; transit bridge scouring & soil saturation",
    ),
}


def _format_rationale(
    event_type: str, delta: str, context: str, station: str
) -> str:
    return f"[{event_type}] | Delta: {delta} | Context: {context} | Station: {station}"


def _reading_payload(reading: dict[str, Any]) -> dict[str, Any]:
    return {
        "city": reading["city"],
        "timestamp": reading["timestamp"],
        "temperature_2m": reading["temperature_2m"],
        "apparent_temperature": reading["apparent_temperature"],
        "precipitation": reading["precipitation"],
        "wind_speed_10m": reading["wind_speed_10m"],
        "weather_code": reading["weather_code"],
    }


class WeatherEvaluationEngine:
    """Deterministic, synchronous evaluation of weather readings against pinned rules."""

    def __init__(self, pool: database.DatabasePool) -> None:
        self._pool = pool

    def evaluate_reading(self, reading: dict[str, Any]) -> list[dict[str, Any]]:
        city = reading["city"]
        events: list[dict[str, Any]] = []

        try:
            if city in TARGET_CITIES:
                events.extend(self._evaluate_target_city(reading))
            if city in UPSTREAM_CITIES:
                events.extend(self._evaluate_upstream_city(reading))
        except (sqlite3.Error, ValueError) as exc:
            logger.exception(
                "Event evaluation failed for city %s at %s",
                city,
                reading.get("timestamp"),
            )
            raise RuntimeError(
                f"Event evaluation failed for {city}: {exc}"
            ) from exc

        return events

    def _evaluate_target_city(self, reading: dict[str, Any]) -> list[dict[str, Any]]:
        city = reading["city"]
        events: list[dict[str, Any]] = []
        payload = _reading_payload(reading)

        if city == "Ottawa":
            events.extend(self._evaluate_thermal_trap(reading, payload))
        if city in CORRIDOR_TARGETS:
            events.extend(self._evaluate_corridor_for_target(reading, payload))
        if city == "Vancouver":
            events.extend(self._evaluate_pacific_surge_for_target(reading, payload))

        events.extend(self._evaluate_severe_cold_snap(reading, payload))
        events.extend(self._evaluate_extreme_heat_wave(reading, payload))
        events.extend(self._evaluate_flood_risks(reading, payload))
        events.extend(self._evaluate_severe_windchill(reading, payload))
        return events

    def _evaluate_upstream_city(self, reading: dict[str, Any]) -> list[dict[str, Any]]:
        city = reading["city"]
        events: list[dict[str, Any]] = []

        if city in CORRIDOR_UPSTREAM:
            events.extend(self._evaluate_corridor_from_upstream(reading))
        if city == "Tofino":
            events.extend(self._evaluate_pacific_surge_from_upstream(reading))
        return events

    def _evaluate_thermal_trap(
        self, reading: dict[str, Any], payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        app_temp = reading["apparent_temperature"]
        precip = reading["precipitation"]
        temp = reading["temperature_2m"]

        if app_temp >= 0.0 or precip <= 2.0 or temp <= -2.0:
            return []

        rationale = _format_rationale(
            "THERMAL_TRAP",
            "Apparent Temp < 0C with active rain",
            "Thermal inversion risk for freezing rain",
            "Ottawa",
        )
        return [
            self._build_event(
                city="Ottawa",
                timestamp=reading["timestamp"],
                event_type="THERMAL_TRAP",
                rationale=rationale,
                payload=payload,
            )
        ]

    def _evaluate_corridor_for_target(
        self, target_reading: dict[str, Any], target_payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if target_reading["precipitation"] >= 2.0:
            return []

        events: list[dict[str, Any]] = []
        timestamp = target_reading["timestamp"]
        target_city = target_reading["city"]

        for upstream_name in ("Windsor", "Chicago"):
            upstream = database.get_reading_at_timestamp(
                self._pool, upstream_name, timestamp
            )
            if upstream is None:
                continue
            if self._corridor_upstream_triggered(upstream):
                events.append(
                    self._corridor_warning_event(
                        target_city=target_city,
                        timestamp=timestamp,
                        upstream_name=upstream_name,
                        payload=target_payload,
                    )
                )
        return events

    def _evaluate_corridor_from_upstream(
        self, upstream_reading: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if not self._corridor_upstream_triggered(upstream_reading):
            return []

        events: list[dict[str, Any]] = []
        timestamp = upstream_reading["timestamp"]
        upstream_name = upstream_reading["city"]
        upstream_payload = _reading_payload(upstream_reading)

        for target_city in ("Toronto", "Ottawa"):
            target = database.get_reading_at_timestamp(
                self._pool, target_city, timestamp
            )
            if target is None or target["precipitation"] >= 2.0:
                continue
            events.append(
                self._corridor_warning_event(
                    target_city=target_city,
                    timestamp=timestamp,
                    upstream_name=upstream_name,
                    payload=upstream_payload,
                )
            )
        return events

    def _corridor_upstream_triggered(self, upstream: dict[str, Any]) -> bool:
        temp_delta = self._one_hour_temperature_delta(upstream)
        if temp_delta is not None and temp_delta < -5.0:
            return True
        return upstream["precipitation"] > 10.0

    def _corridor_warning_event(
        self,
        target_city: str,
        timestamp: str,
        upstream_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        rationale = _format_rationale(
            "CORRIDOR_WARNING",
            "Temp Drop or Heavy Rain Upstream",
            "Front moving from Windsor corridor toward Toronto",
            upstream_name,
        )
        return self._build_event(
            city=target_city,
            timestamp=timestamp,
            event_type="CORRIDOR_WARNING",
            rationale=rationale,
            payload=payload,
        )

    def _evaluate_pacific_surge_for_target(
        self, target_reading: dict[str, Any], target_payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if target_reading["wind_speed_10m"] >= 25.0:
            return []

        timestamp = target_reading["timestamp"]
        tofino = database.get_reading_at_timestamp(self._pool, "Tofino", timestamp)
        if tofino is None:
            return []
        if not self._pacific_upstream_triggered(tofino):
            return []

        rationale = _format_rationale(
            "PACIFIC_SURGE",
            "High Wind and Rain Coastline",
            "Pacific storm front detected at Tofino; moving mainland",
            "Tofino",
        )
        return [
            self._build_event(
                city="Vancouver",
                timestamp=timestamp,
                event_type="PACIFIC_SURGE",
                rationale=rationale,
                payload=target_payload,
            )
        ]

    def _evaluate_pacific_surge_from_upstream(
        self, upstream_reading: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if not self._pacific_upstream_triggered(upstream_reading):
            return []

        timestamp = upstream_reading["timestamp"]
        vancouver = database.get_reading_at_timestamp(
            self._pool, "Vancouver", timestamp
        )
        if vancouver is None or vancouver["wind_speed_10m"] >= 25.0:
            return []

        rationale = _format_rationale(
            "PACIFIC_SURGE",
            "High Wind and Rain Coastline",
            "Pacific storm front detected at Tofino; moving mainland",
            "Tofino",
        )
        return [
            self._build_event(
                city="Vancouver",
                timestamp=timestamp,
                event_type="PACIFIC_SURGE",
                rationale=rationale,
                payload=_reading_payload(upstream_reading),
            )
        ]

    def _pacific_upstream_triggered(self, upstream: dict[str, Any]) -> bool:
        return (
            upstream["wind_speed_10m"] > 50.0 and upstream["precipitation"] > 15.0
        )

    def _evaluate_severe_cold_snap(
        self, reading: dict[str, Any], payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        city = reading["city"]
        threshold, context = SCS_THRESHOLDS[city]
        temp = reading["temperature_2m"]
        if temp >= threshold:
            return []

        delta = f"{temp:.1f}C"
        rationale = _format_rationale("SCS", delta, context, city)
        return [
            self._build_event(
                city=city,
                timestamp=reading["timestamp"],
                event_type="SCS",
                rationale=rationale,
                payload=payload,
            )
        ]

    def _evaluate_extreme_heat_wave(
        self, reading: dict[str, Any], payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        city = reading["city"]
        threshold, context = EHW_THRESHOLDS[city]
        temp = reading["temperature_2m"]
        if temp <= threshold:
            return []

        delta = f"{temp:.1f}C"
        rationale = _format_rationale("EHW", delta, context, city)
        return [
            self._build_event(
                city=city,
                timestamp=reading["timestamp"],
                event_type="EHW",
                rationale=rationale,
                payload=payload,
            )
        ]

    def _evaluate_flood_risks(
        self, reading: dict[str, Any], payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        city = reading["city"]
        precip = reading["precipitation"]
        events: list[dict[str, Any]] = []

        sfr_threshold, sfr_context = SFR_THRESHOLDS[city]
        if precip >= sfr_threshold:
            delta = f"{precip:.1f}mm"
            rationale = _format_rationale("SFR", delta, sfr_context, city)
            events.append(
                self._build_event(
                    city=city,
                    timestamp=reading["timestamp"],
                    event_type="SFR",
                    rationale=rationale,
                    payload=payload,
                )
            )
            return events

        mfr_threshold, mfr_context = MFR_THRESHOLDS[city]
        if precip >= mfr_threshold:
            delta = f"{precip:.1f}mm"
            rationale = _format_rationale("MFR", delta, mfr_context, city)
            events.append(
                self._build_event(
                    city=city,
                    timestamp=reading["timestamp"],
                    event_type="MFR",
                    rationale=rationale,
                    payload=payload,
                )
            )
        return events

    def _evaluate_severe_windchill(
        self, reading: dict[str, Any], payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        app_temp = reading["apparent_temperature"]
        if app_temp >= -30.0:
            return []

        delta = f"{app_temp:.1f}C"
        rationale = _format_rationale(
            "SEVERE_WINDCHILL",
            delta,
            "Severe windchill hazard across exposed infrastructure",
            reading["city"],
        )
        return [
            self._build_event(
                city=reading["city"],
                timestamp=reading["timestamp"],
                event_type="SEVERE_WINDCHILL",
                rationale=rationale,
                payload=payload,
            )
        ]

    def _one_hour_temperature_delta(self, reading: dict[str, Any]) -> float | None:
        prior = database.get_reading_before_timestamp(
            self._pool,
            reading["city"],
            reading["timestamp"],
        )
        if prior is None:
            return None
        return reading["temperature_2m"] - prior["temperature_2m"]

    def _build_event(
        self,
        city: str,
        timestamp: str,
        event_type: str,
        rationale: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "city": city,
            "timestamp": timestamp,
            "event_type": event_type,
            "rationale": rationale,
            "payload_snapshot": payload,
        }
