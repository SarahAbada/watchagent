# Data Immutability & Deduplication Conventions

## Context
Data integrity requires strict data deduplication before writing to the SQLite database. Furthermore, financial and infrastructure patterns demand that historical records remain completely immutable once written.

## Proactive Deduplication Protocol
- **Pre-Write Verification:** Before performing an insert into the `weather_readings` table, the application must query the database for the most recent record matching that specific city:
  ```sql
  SELECT timestamp FROM weather_readings WHERE city = ? ORDER BY timestamp DESC LIMIT 1;
  ```
- **Execution Condition:** Compare the upstream payload's timestamp against this retrieved database timestamp. 
  - If the timestamps match: The reading is an expected duplicate. Silently drop the execution cycle without attempting a database write. 
  - If the timestamps differ (or no records exist): Proceed with the database write.

## Silent Skipping & Noise Suppression
- **Zero Duplicate Logging:** Do not log standard `INFO`, `WARNING`, or `DEBUG` lines for expected duplicate timestamp skips. Keep the operational log outputs clean and dense.
- **Traceability:** To verify daemon health without log noise, allow the metrics collection layer to track successful/failed poll loops natively via the `polling_metrics` table or the `/health` API endpoint.

## Absolute Immutability Constraints
- **Forbidden SQL Paradigms:** Cursor is strictly prohibited from writing or generating code that utilizes `UPDATE` or `DELETE` SQL commands against the `weather_readings` or `notable_events` tables.
- **Repository Pattern Enforcement:** The data access layer/repository classes must only expose write methods (`insert_reading`, `insert_event`) and read methods (`get_readings`, `get_events`). No modification or deletion methods may be declared.
- **Separation of Concerns:** This rule file governs data storage constraints only. The structural derivation and calculation of the `rationale` field must be governed exclusively by the dedicated weather event logic rule file.
