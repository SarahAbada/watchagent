# Poller Error Handling & Resiliency Conventions

## Context
This project polls an external, unauthenticated third-party weather API (`://open-meteo.com`). Local network drops, upstream rate limiting, or transient outages must not crash the background daemon, nor should they flood disk space with infinite error traces or expose the system to log-injection attacks.

## Resiliency, Retry, and Recovery Logic
- **Retriable Errors (5xx, Timeouts, Connection Drops, 429):** Intercept these, execute the capped backoff protocol, and continue the polling loop.
- **Fatal Errors (400, 404, 422, Malformed Payloads):** Do not let these loop infinitely or crash the entire daemon. Execute a **Clean State Reset** for that specific city tracking loop using these exact steps:
  1. Immediately close and discard the current active HTTP client/session instance for that city.
  2. Clear all local in-memory caches, active request configurations, and temporary query string variables for that city.
  3. Purge any uncommitted or corrupted database transactions tied to that cycle.
  4. Wait a mandatory 5-minute cooldown isolation period.
  5. Initialize a completely fresh HTTP client session instance and resume polling.
- **Capped Exponential Backoff:** For retriable errors, implement backoff using $wait = \min(2^{retry\_count}, 60)$ seconds. Never allow the backoff interval to exceed 60 seconds.

## Structured and Sanitized Logging Contract
- **Log Sanitization Security Protocol:** Before any request payload, URL, or error string is written to the logs, it must be stripped of all newline (`\n`) and carriage return (`\r`) characters to prevent log-injection forging. Any SQL/script-vulnerable characters must be escaped or neutralized.
- **Retriable Error Format:** Log at `WARNING` level using this exact tokenized format:
  `[POLL_WARNING] City: <city_name> | Action: RETRYING | Error: <exception_class/status_code> | Attempt: <retry_count> | Wait: <backoff_seconds>s | Request: <sanitized_url_and_payload>`
- **Fatal Error Format:** Log at `CRITICAL` level using this exact tokenized format:
  `[POLL_CRITICAL] City: <city_name> | Action: STATE_RESET | Reason: <error_message> | Request: <sanitized_url_and_payload>`

## Metrics Aggregation (Short-Term Logs vs. Long-Term State)
- **Log Rotation:** Configure a `RotatingFileHandler` keeping a maximum of 3 days of raw logs or 10MB total file size. Old raw logs must be automatically purged.
- **State Database Persistence:** Upon every completed poll cycle (success or failure), increment the historical tracking metrics counters in the database (`total_polls`, `failed_polls`, `timestamp_hour`). Do not let log rotation erase long-term availability records.

## Daemon Lifecycle
- **Graceful Shutdown:** Intercept `SIGINT` and `SIGTERM`. Cleanly break loop execution, complete transactions currently in flight, close database connection pools, and exit with status `0` without printing raw python stack traces to stdout.
