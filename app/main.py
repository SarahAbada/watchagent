"""WatchAgent HTTP API and process entry point."""

from __future__ import annotations

import logging
import os
import signal
import sqlite3
import sys

from flask import Flask, jsonify, request

from app import database
from app.logging_config import configure_logging
from app.poller import WeatherPoller

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.json.sort_keys = False
_poller: WeatherPoller | None = None


def _parse_limit(raw_limit: str | None, default: int = 50) -> int:
    if raw_limit is None:
        return default
    try:
        return int(raw_limit)
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc


@app.route("/health", methods=["GET"])
def health() -> tuple[object, int]:
    try:
        pool = database.get_pool()
        snapshot = database.get_health_snapshot(pool)
        contract_payload = {
            "status": "ok",
            "readings_stored": int(snapshot["readings_count"]),
            "events_stored": int(snapshot["events_count"]),
        }
        return jsonify(contract_payload), 200
    except (sqlite3.Error, TimeoutError, RuntimeError, ValueError) as exc:
        logger.exception("Health check failed")
        return (
            jsonify({"status": "unhealthy", "error": str(exc)}),
            503,
        )


@app.route("/events", methods=["GET"])
def events() -> tuple[object, int]:
    city = request.args.get("city")
    limit_param = request.args.get("limit")

    try:
        limit = _parse_limit(limit_param)
        pool = database.get_pool()
        rows = database.get_events(pool, city=city, limit=limit)
        return jsonify({"events": rows}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except (sqlite3.Error, TimeoutError, RuntimeError) as exc:
        logger.exception("Failed to fetch events")
        return jsonify({"error": str(exc)}), 500


@app.route("/readings", methods=["GET"])
def readings() -> tuple[object, int]:
    city = request.args.get("city")
    limit_param = request.args.get("limit")

    try:
        limit = _parse_limit(limit_param)
        pool = database.get_pool()
        rows = database.get_readings(pool, city=city, limit=limit)
        return jsonify({"readings": rows}), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except (sqlite3.Error, TimeoutError, RuntimeError) as exc:
        logger.exception("Failed to fetch readings")
        return jsonify({"error": str(exc)}), 500


def _shutdown_handler(signum: int, _frame: object | None) -> None:
    logger.info("Shutdown signal received: %s", signum)
    global _poller
    if _poller is not None:
        _poller.stop()
    database.close_pool()
    sys.exit(0)


def create_app() -> Flask:
    return app


def main() -> None:
    configure_logging()
    global _poller

    pool = database.get_pool()
    interval_raw = os.environ.get("POLL_INTERVAL_SECONDS", "300")
    try:
        poll_interval = int(interval_raw)
    except ValueError as exc:
        raise ValueError("POLL_INTERVAL_SECONDS must be an integer") from exc
    if poll_interval < 1:
        raise ValueError("POLL_INTERVAL_SECONDS must be at least 1")

    _poller = WeatherPoller(pool, poll_interval_seconds=poll_interval)
    _poller.start()

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port_raw = os.environ.get("FLASK_PORT", "5000")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError("FLASK_PORT must be an integer") from exc

    logger.info("Starting Flask server on %s:%s", host, port)
    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    finally:
        if _poller is not None:
            _poller.stop()
        database.close_pool()


if __name__ == "__main__":
    main()
