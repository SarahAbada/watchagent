# WatchAgent: Rubric-Aligned Testing & CI Conventions

## Context
Unit and integration tests must strictly validate the core evaluation criteria of the assignment, focusing heavily on event detection logic, deduplication invariants, and exact API contract structures. This validation must happen under real-world production realities—including WAL behavior, strict constraints, and thread safety—using isolated local filesystems that mock out all third-party networks.

## 1. Core Evaluation Testing Priorities (Rubric Alignment)
- **Event Detection Logic (Highest Priority):** Tests must construct a controlled chronological sequence of mock weather readings. They must assertively verify that the detection engine fires the events expected (e.g., asymmetric thresholds, corridor warnings) and explicitly does NOT fire events when thresholds are missed. These tests must serve as a direct expression of your meteorological reasoning.
- **API Contract & Shape Validation:** Tests must seed a test database and assert that `/health`, `/readings`, and `/events` return the precise JSON object structures, key names (`readings_stored`, `events_stored`), and filtering/limit behaviors mandated by section 03 of the assignment sheet.
- **Deduplication Verification:** Tests must mock the external weather API to return the exact same hourly reading timestamp twice sequentially, asserting that the repository tier cleanly skips the redundant record and that the total table count remains exactly one.
- **Immutability Protection:** Assert that any manual attempt to call an `UPDATE` or `DELETE` string pattern inside your repositories immediately raises an operational exception.

## 2. Test Environment & Physical Database Isolation
- **Physical Temp Files Only:** Do not use in-memory SQLite databases (`:memory:`). Tests must strictly execute against temporary physical `.db` files created dynamically on disk.
- **Lifecycle Isolation:** 
  - Every test class or execution track must generate a unique, temporary database file path utilizing Python's `tempfile` module.
  - The testing framework must apply all production optimization pragmas (`PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, `PRAGMA foreign_keys=ON;`) onto the temporary file prior to testing.
- **Teardown Purge:** Upon completion or test failure, the framework must explicitly delete and purge the temporary `.db` file along with its `.db-wal` and `.db-shm` sidecar artifacts to maintain clean host storage states.

## 3. Network Isolation
- **100% Offline Network Isolation:** Under no circumstances may any test suite execution send a live network request to `://open-meteo.com`. All third-party endpoints must be stubbed using `unittest.mock`.

## 4. Continuous Integration Pipeline (GitHub Actions)
- **Execution Triggers:** The CI pipeline configuration must execute automatically on every push or pull request to the `main` branch.
- **The Two-Job Mandate:** The pipeline must split into two parallel validation blocks:
  1. **Job 1 (Test)**: Pulls a clean Python environment, installs dependencies, and executes the local unit testing suite using the isolation and rubric parameters defined above.
  2. **Job 2 (Build)**: Triggers a clean `docker build` to confirm the container compiles perfectly without requiring environment keys or exposing local configurations.
