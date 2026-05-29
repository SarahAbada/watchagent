"""Synchronous background poller for Open-Meteo current conditions."""

from __future__ import annotations

import json
import logging
import math
import signal
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlencode
from datetime import datetime, timezone
from typing import Any

from app import database
from app.logging_config import sanitize_log_value

logger = logging.getLogger(__name__)

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"
CURRENT_FIELDS = (
    "temperature_2m,apparent_temperature,precipitation,"
    "wind_speed_10m,weather_code"
)
DEFAULT_POLL_INTERVAL_SECONDS = 300
FATAL_COOLDOWN_SECONDS = 300
HTTP_TIMEOUT_SECONDS = 30
MAX_BACKOFF_SECONDS = 60

RETRIABLE_STATUS_CODES = frozenset({429}) | set(range(500, 600))
FATAL_STATUS_CODES = frozenset({400, 404, 422})

CITIES: tuple[dict[str, str | float], ...] = (
    {"name": "Ottawa", "latitude": 45.42, "longitude": -75.69},
    {"name": "Toronto", "latitude": 43.70, "longitude": -79.42},
    {"name": "Vancouver", "latitude": 49.25, "longitude": -123.12},
)


def build_forecast_url(latitude: float, longitude: float) -> str:
    """Build a raw Open-Meteo forecast URL with unescaped query separators."""
    query = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": CURRENT_FIELDS,
            "wind_speed_unit": "kmh",
            "timezone": "auto",
        }
    )
    return f"{OPEN_METEO_BASE}?{query}"


def sanitize_url_for_log(url: str) -> str:
    """Strip log-injection newlines only; preserve raw ampersands in query strings."""
    return url.replace("\n", "").replace("\r", "")


def capped_backoff_seconds(retry_count: int) -> int:
    return min(int(math.pow(2, retry_count)), MAX_BACKOFF_SECONDS)


@dataclass
class CitySession:
    name: str
    latitude: float
    longitude: float
    request_url: str = field(init=False)
    opener: urllib.request.OpenerDirector | None = None
    retry_count: int = 0
    in_fatal_cooldown: bool = False

    def __post_init__(self) -> None:
        self.request_url = build_forecast_url(self.latitude, self.longitude)

    def reset_http_client(self) -> None:
        self.opener = None

    def ensure_opener(self) -> urllib.request.OpenerDirector:
        if self.opener is None:
            self.opener = urllib.request.build_opener()
        return self.opener


class WeatherPoller:
    """Background daemon that polls Open-Meteo and persists readings."""

    def __init__(
        self,
        pool: database.DatabasePool,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._pool = pool
        self._poll_interval_seconds = poll_interval_seconds
        self._shutdown_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._sessions: dict[str, CitySession] = {
            str(city["name"]): CitySession(
                name=str(city["name"]),
                latitude=float(city["latitude"]),
                longitude=float(city["longitude"]),
            )
            for city in CITIES
        }
        self._sessions_lock = threading.Lock()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._shutdown_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="weather-poller",
            daemon=True,
        )
        self._thread.start()
        logger.info("Weather poller started")

    def stop(self, timeout: float = 35.0) -> None:
        self._shutdown_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("Poller thread did not stop before timeout")
            else:
                logger.info("Weather poller stopped")

    def install_signal_handlers(self) -> None:
        def handle_signal(signum: int, _frame: object | None) -> None:
            logger.info("Received signal %s; initiating graceful shutdown", signum)
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    def _run_loop(self) -> None:
        while not self._shutdown_event.is_set():
            for city_name in ("Ottawa", "Toronto", "Vancouver"):
                if self._shutdown_event.is_set():
                    break
                self._poll_city(city_name)
            self._shutdown_event.wait(self._poll_interval_seconds)

    def _poll_city(self, city_name: str) -> None:
        with self._sessions_lock:
            session = self._sessions[city_name]

        if session.in_fatal_cooldown:
            return

        cycle_timestamp = datetime.now(timezone.utc).isoformat()
        poll_failed = False

        try:
            while not self._shutdown_event.is_set():
                try:
                    payload = self._fetch_current(session)
                    self._persist_reading(session.name, payload)
                    session.retry_count = 0
                    poll_failed = False
                    break
                except _RetriablePollError as exc:
                    poll_failed = True
                    wait_seconds = capped_backoff_seconds(session.retry_count)
                    logger.warning(
                        "[POLL_WARNING] City: %s | Action: RETRYING | Error: %s | "
                        "Attempt: %s | Wait: %ss | Request: %s",
                        session.name,
                        sanitize_log_value(exc.error_token),
                        session.retry_count,
                        wait_seconds,
                        sanitize_url_for_log(session.request_url),
                    )
                    session.retry_count += 1
                    if self._shutdown_event.wait(wait_seconds):
                        break
                except _FatalPollError as exc:
                    poll_failed = True
                    logger.critical(
                        "[POLL_CRITICAL] City: %s | Action: STATE_RESET | Reason: %s | "
                        "Request: %s",
                        session.name,
                        sanitize_log_value(exc.reason),
                        sanitize_url_for_log(session.request_url),
                    )
                    self._execute_clean_state_reset(session)
                    break
        except sqlite3.Error:
            poll_failed = True
            logger.exception(
                "Database error during poll cycle for city: %s",
                city_name,
            )
        finally:
            try:
                database.record_poll_cycle(
                    self._pool,
                    cycle_timestamp,
                    failed=poll_failed,
                )
            except sqlite3.Error:
                logger.exception(
                    "Failed to record polling metrics for city: %s",
                    city_name,
                )

    def _fetch_current(self, session: CitySession) -> dict[str, Any]:
        opener = session.ensure_opener()
        request_url = build_forecast_url(session.latitude, session.longitude)
        session.request_url = request_url
        request = urllib.request.Request(
            request_url,
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                status_code = response.getcode()
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            body = exc.read().decode("utf-8", errors="replace")
            if status_code in FATAL_STATUS_CODES:
                raise _FatalPollError(
                    f"HTTP {status_code}",
                ) from exc
            if status_code in RETRIABLE_STATUS_CODES:
                raise _RetriablePollError(f"HTTP {status_code}") from exc
            raise _FatalPollError(f"Unhandled HTTP status {status_code}") from exc
        except urllib.error.URLError as exc:
            raise _RetriablePollError(exc.__class__.__name__) from exc
        except TimeoutError as exc:
            raise _RetriablePollError("TimeoutError") from exc

        if status_code in FATAL_STATUS_CODES:
            raise _FatalPollError(f"HTTP {status_code}")
        if status_code in RETRIABLE_STATUS_CODES:
            raise _RetriablePollError(f"HTTP {status_code}")
        if status_code < 200 or status_code >= 300:
            raise _FatalPollError(f"HTTP {status_code}")

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise _FatalPollError("Malformed JSON payload") from exc

        return self._parse_current_block(session.name, decoded)

    def _parse_current_block(
        self, city_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        current = payload.get("current")
        if not isinstance(current, dict):
            raise _FatalPollError("Missing current object in payload")

        timestamp = current.get("time")
        required_fields = (
            "temperature_2m",
            "apparent_temperature",
            "precipitation",
            "wind_speed_10m",
            "weather_code",
        )
        for field_name in required_fields:
            if field_name not in current:
                raise _FatalPollError(f"Missing field: {field_name}")

        try:
            return {
                "city": city_name,
                "timestamp": str(timestamp),
                "temperature_2m": float(current["temperature_2m"]),
                "apparent_temperature": float(current["apparent_temperature"]),
                "precipitation": float(current["precipitation"]),
                "wind_speed_10m": float(current["wind_speed_10m"]),
                "weather_code": int(current["weather_code"]),
            }
        except (TypeError, ValueError) as exc:
            raise _FatalPollError("Invalid field types in current payload") from exc

    def _persist_reading(self, city_name: str, reading: dict[str, Any]) -> None:
        latest = database.get_latest_timestamp(self._pool, city_name)
        incoming_timestamp = reading["timestamp"]
        if latest is not None and latest == incoming_timestamp:
            return

        database.insert_reading(
            self._pool,
            city=city_name,
            timestamp=incoming_timestamp,
            temperature_2m=reading["temperature_2m"],
            apparent_temperature=reading["apparent_temperature"],
            precipitation=reading["precipitation"],
            wind_speed_10m=reading["wind_speed_10m"],
            weather_code=reading["weather_code"],
        )
        logger.info(
            "Stored reading for %s at %s",
            city_name,
            sanitize_log_value(incoming_timestamp),
        )

    def _execute_clean_state_reset(self, session: CitySession) -> None:
        session.reset_http_client()
        session.retry_count = 0
        session.request_url = build_forecast_url(session.latitude, session.longitude)
        try:
            database.rollback_idle_transaction(self._pool)
        except (sqlite3.Error, TimeoutError, RuntimeError):
            logger.exception(
                "Failed to purge uncommitted transactions during state reset for %s",
                session.name,
            )

        session.in_fatal_cooldown = True
        deadline = time.monotonic() + FATAL_COOLDOWN_SECONDS
        while time.monotonic() < deadline:
            if self._shutdown_event.is_set():
                break
            remaining = deadline - time.monotonic()
            self._shutdown_event.wait(min(1.0, max(0.0, remaining)))
        session.in_fatal_cooldown = False
        session.ensure_opener()
        logger.info("Resumed polling for %s after state reset cooldown", session.name)


class _RetriablePollError(Exception):
    def __init__(self, error_token: str) -> None:
        self.error_token = error_token
        super().__init__(error_token)


class _FatalPollError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)
