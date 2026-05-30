# WatchAgent: Weather Monitor & Infrastructure Risk Engine
> **WatchAgent Engineering Overview & Architecture Defense Walkthrough**  
> 🎥 [Watch the 17-Minute Video Presentation on YouTube](https://youtu.be/ZVoXCzveHPI)

WatchAgent is a security-first, high-reliability infrastructure monitoring daemon and HTTP API written in Python 3.11+. The service continuously orchestrates weather ingestion loops across Canadian economic corridors, executes deterministic micro-climate risk assessment modeling, and exposes historical intelligence metrics through a structured, authenticated-parity endpoint array.
## 1. System Architecture & Visualization
WatchAgent isolates data collection, state tracking, and delivery surfaces. The system operates entirely synchronously to enforce solid transactional boundaries and guarantee crash resilience during container or power grid brownouts.
```text
       [ External Open-Meteo API ]
                    │
                    ▼ (urllib.request / 1-Min Poll Loop)
   ┌─────────────────────────────────────────────────┐
   │ app/poller.py (Background Orchestration Daemon) │
   └────────────────────────┬────────────────────────┘
                            │
               (Proactive Deduplication)
             ORDER BY timestamp DESC LIMIT 1
                            │
                            ▼
   ┌─────────────────────────────────────────────────┐
   │ app/database.py (SQLite Pool with WAL/NORMAL)  │◄───┐
   └────────────────────────┬────────────────────────┘    │
                            │                             │
             (If Unique Timestamp Committed)              │ (Context Queries:
                            │                             │  Prior 2 Hours /
                            ▼                             │  Upstream Rows)
   ┌─────────────────────────────────────────────────┐    │
   │ app/engine.py (Meteorological Evaluation Engine)├────┘
   └────────────────────────┬────────────────────────┘
                            │
               (Triggered Notable Events)
                            │
                            ▼
   ┌─────────────────────────────────────────────────┐
   │ app/main.py (Synchronous Flask Delivery Tier)   │
   └────────────────────────┬────────────────────────┘
                            │
                            ▼
                 [ http://localhost:8000 ]
                     (/health, /readings, /events)
```
### Component Interconnections
1. **`app/poller.py`**: Executes a continuous timed schedule to hit `://open-meteo.com` for target and upstream regional networks. Before executing a write, it issues a single-row lookback query to drop matching timestamps silently.
2. **`app/database.py`**: Configures an embedded SQLite engine wrapped in Write-Ahead Logging (`WAL`) mode to prevent filesystem truncation or corruption during hardware power drops.
3. **`app/engine.py`**: A pure, stateless business module that accepts the newly stored reading, extracts historical baseline intervals from the data pool, identifies anomalies, and yields event mappings.
4. **`app/main.py`**: Operates as a strict HTTP delivery web service exposing the state of collected readings and generated alerts.
## 2. Technology Choices & Justification
### Python 3.11+ (Synchronous Paradigm)
*   **Justification:** While modern web tasks favor asynchronous (`asyncio`) architectures, this infrastructure system prioritizes **predictability and determinism**. Async loops introduce race conditions during database write contentions and make UNIX lifecycle signaling hard to coordinate safely. A synchronous model guarantees that transaction states are isolated and atomic.
### SQLite (WAL & Normal Synchronous Pragmas)
*   **Justification:** Deploying an external network database (such as PostgreSQL) introduces a secondary layer of failure (broken network bridges, container boot ordering issues). SQLite is a local file asset, ensuring that if the application container has power, the storage layer has power. By forcing `PRAGMA journal_mode=WAL;` and `PRAGMA synchronous=NORMAL;`, the engine commits adjustments to an append-only sidecar log file, neutralizing database corruption parameters upon sudden power termination.
### Flask (Synchronous Runtime)
*   **Justification:** Flask is standard, lightweight, and operates natively in a synchronous worker pool. It provides an optimal layer for routing parameters without pulling in heavy, unneeded asynchronous dependencies.
## 3. Meteorological Event Engine Rationale
A system that triggers alerts based on uniform, global thresholds is intellectually shallow and fails to provide meaningful operational intelligence. WatchAgent treats weather risks as **asymmetric, relative, and infrastructure-dependent**.

### A. Asymmetrical Temperature Shocks (`SCS` & `EHW`)
Infrastructure failure thresholds are tied to local historical baselines, not arbitrary global numbers:
*   **Severe Cold Snap (`SCS`)**: Set to **<-25°C** in Ottawa (continental grid capacity limit), **<-18°C** in Toronto (transit switch vulnerability boundary), and **<-5°C** in Vancouver. Because maritime Vancouver rarely experiences deep freezes, residential plumbing and city mains are buried shallowly; a sustained -5°C freeze causes massive pipe-burst epidemics.
*   **3-Hour Persistence Requirement**: To balance sensitivity and noise, the engine completely ignores brief single-hour afternoon spikes or sensor anomalies. An alert *only* fires if a temperature breach is sustained continuously for **3 consecutive hours**, representing true infrastructural stress.

### B. Upstream Early-Warning Corridor Alerts (`CORRIDOR_WARNING` & `PACIFIC_SURGE`)
WatchAgent actively pulls weather parameters from geographic early-warning points to predict storms before they strike target cities:
*   **Windsor-Toronto Corridor**: Low-pressure systems ("Colorado Lows") consistently funnel tracking streams through Windsor/Chicago eastward into Toronto and Ottawa. If Windsor or Chicago logs a temperature plummet (greater than 5.0°C drop) or heavy rain (greater than 10.0mm), but Toronto is currently clear (less than 2.0mm), a high-probability corridor warning is flagged.
*   **Pacific Maritime Guard**: Intense atmospheric rivers traveling across the Pacific hit Tofino (outer edge of Vancouver Island) hours before crossing the mainland. If Tofino registers severe gale winds (greater than 50.0 km/h) and intense rain (greater than 15.0mm), but Vancouver is calm (less than 25.0 km/h), an Atmospheric River Alert is triggered to signify an impending mainland storm surge.

### C. Accumulation and Risk Cascades (`FLASH_FREEZE` & `SFR`)
*   **Rapid Flash Freeze (`FLASH_FREEZE`)**: This logic monitors the highly dangerous intersection of precipitation and plummeting Arctic air masses. If a city has a wet baseline (active or immediate past hour rain) and the temperature plummets by more than 5.0°C within an hour into below-freezing territory (less than 0.0°C), the system flags an immediate flash freeze warning, denoting extreme black ice glazing risks on roads and transit cables.
*   **Differentiated Flash Flooding**: Rain thresholds map directly to urbanization. Toronto's high concrete concentration and low-lying ravine rail grids mean that an intensity of **25mm/hr** triggers Severe Flood Risk (`SFR`) (the critical threshold for shutting down major corridors like the Don Valley Parkway). Vancouver's heavily engineered coastal mountain spillways handle high volumes natively, pushing its `SFR` ceiling to **50mm/hr**.
## 4. Cursor Workspace Setup
The development lifecycle of this project was systematically sandboxed using dedicated Cursor rule configurations, modular agent logic, and automation tools committed to version control.

### Rule Files Configured (`.cursor/rules/`)
1.  **`poller-resiliency.md`**: Enforces strict retriable error sorting (5xx Timeouts invoke a capped exponential backoff (wait = min(2^n, 60)) while forcing malformed 4xx client payloads to trigger immediate isolated clean state resets. Defines log sanitization security protocols to strip `\n` and `\r` tokens, neutralizing log-injection.
2.  **`database-schema.md`**: Dictates database architecture constraints. Hard-codes the exact table spaces and unique constraints, bans runtime schema modification keywords (`DROP`, `ALTER`), and mandates parameterized placeholders (`?`) to completely eliminate SQL injection vectors.
3.  **`data-immutability.md`**: Enforces our pre-write timestamp verification pattern. Forbids generating code matching `UPDATE` or `DELETE` string expressions, ensuring database histories remain strictly read/write append-only logs.
4.  **`event-detection.md`**: Holds our complete meteorological formula matrices, hard thresholds, and tokenized string output constraints.

### Custom Agents (`.cursor/agents/`)
1.  **`systems-architect.json`**: Scoped as our principal core infrastructure programmer. Enforces synchronous execution invariants, parameterized operations, signal trapping routines, and strictly bans the native Python `print()` function to guarantee 100% telemetry routing compliance.
2.  **`meteorological-agent.json`**: Scoped as our weather logic and analytical testing reviewer. Validates math delta parameters, ensures thresholds are evaluated asymmetrically based on city infrastructure assets, and enforces tokenized compliance.

### Custom Executable Skills (`.cursor/skills/`)
*   **`analyze_data.py`**: A fully automated Python tool that queries the live persistent database to process hourly aggregated tracking metrics, run trend summaries, run per-city weather bounds analysis, and execute data deduplication integrity tracking scans.


*   **`replay_events.py`**: A custom simulation skill tool that lazily streams rows directly from the local weather table, passing data through our advanced detection loop to calculate historical event frequency and output calculated system Signal-to-Noise Ratios (SNR).

------------------------------
## 5. Local Setup & Execution (Without Docker)
### Prerequisites

* Python 3.11+
* Virtual environment engine (venv)

### Execution Workflow

### 1. Initialize virtual space and install locked framework dependencies
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
### 2. Configure operational workspace variables
```
export DATABASE_PATH="./data/weather.db"
export LOG_DIR="./logs"
```
### 3. Boot the application engine stack
```
python -m app.main

```
### Running Tests Locally
To execute the mock-insulated 16-test diagnostic suite completely offline:

`.venv/bin/pytest -v `

------------------------------
## 6. Docker & Container Management
The WatchAgent pipeline maps configurations via external host volume attachments, guaranteeing total persistence across container lifecycles.
### Rebuilding and Launching from a Clean Clone

### 1. Clone the repository and establish standard local configuration shapes
```
git clone 
cd watchagent
cp .env.example .env
```
### 2. Fully destroy any lingering Docker layers, caches, or dangling volumes
`docker compose down --volumes --remove-orphans`
### 3. Execute a fresh production build and bring up the system stack
`docker compose up --build`
The background polling daemon will spin up instantly. The HTTP delivery server maps host port 8000 to container runtime environments cleanly.

------------------------------
## 7. API Reference & Verification Queries
You can audit your operational data states using these standard curl commands:

### 1. Query System Heartbeat Metrics and Exact Documented Key Counts
`curl -i http://localhost:8000/health`

Returns: `200 OK {"status": "ok", "readings_stored": 124, "events_stored": 2}`
### 2. Query Raw Logged Conditions for a Targeted City with Limit Constraints
`curl -i "http://localhost:8000/readings?city=Ottawa&limit=3"`
### 3. Query Generated Intelligence Alerts Ordered Most Recent First
`curl -i "http://localhost:8000/events?limit=5"`


