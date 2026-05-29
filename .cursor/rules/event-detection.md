# WatchAgent: Deterministic Event Detection Rules

This document defines the architectural standards for weather event detection within the WatchAgent service. All detection logic must be deterministic, synchronous, and rely on mathematical deltas between target cities and upstream warning stations.

## 1. Upstream Early-Warning Logic

Detection logic leverages "Upstream Cities" that physically dictate weather patterns for target cities due to regional storm tracks, corridor funnels, or Pacific maritime surges.

### A. Windsor-Toronto Corridor Warning (Target: Toronto/Ottawa)
*   **Meteorological Basis**: Powerful winter storm cells and low-pressure tracking systems pick up moisture and move through the Windsor-Chicago corridor before hitting the Greater Toronto Area.
*   **Logic**:
    - IF `upstream_city` (Windsor OR Chicago) has a 1-hour temperature drop (`temperature_2m` delta) < -5°C OR current `precipitation` > 10.0mm.
    - AND `target_city` (Toronto) current `precipitation` < 2.0mm (Event hasn't arrived yet).
    - **Action**: Flag High-Probability Corridor Warning.
*   **Strict Rationale Format**: `[CORRIDOR_WARNING] | Delta: Temp Drop or Heavy Rain Upstream | Context: Front moving from Windsor corridor toward Toronto | Station: <upstream_city_name>`

### B. Ottawa Valley Thermal Trap (Target: Ottawa)
*   **Meteorological Basis**: The Ottawa Valley traps low-level cold air. When warm, moisture-rich air rides over top, it causes severe ice storms and freezing rain.
*   **Logic**:
    - IF `apparent_temperature` < 0.0°C.
    - AND `precipitation` > 2.0mm.
    - AND `temperature_2m` > -2.0°C (Indicates an active thermal inversion zone risk).
    - **Action**: Flag Freezing Rain / Thermal Trap Risk.
*   **Strict Rationale Format**: `[THERMAL_TRAP] | Delta: Apparent Temp < 0C with active rain | Context: Thermal inversion risk for freezing rain | Station: Ottawa`

### C. Pacific Atmospheric River Surge (Target: Vancouver)
*   **Meteorological Basis**: Vancouver has an intense maritime climate driven by Pacific atmospheric rivers. Tofino, on the outer coast of Vancouver Island, acts as the direct frontline sensor.
*   **Logic**:
    - IF `upstream_city` (Tofino) `wind_speed_10m` > 50.0 km/h AND `precipitation` > 15.0mm.
    - AND `target_city` (Vancouver) `wind_speed_10m` < 25.0 km/h (Surge has not hit the mainland valley yet).
    - **Action**: Flag Atmospheric River Alert.
*   **Strict Rationale Format**: `[PACIFIC_SURGE] | Delta: High Wind and Rain Coastline | Context: Pacific storm front detected at Tofino; moving mainland | Station: Tofino`

## 2. General Notable Events (All Target Cities)
- **Extreme Heatwave**: Triggered when `temperature_2m` > 32.0°C.
- **Urban Flash Flood Risk**: Triggered when `precipitation` > 25.0mm in a single hourly reading window.
- **Moderate Flash Flood Risk**: Triggered when `precipitation` > 15.0mm in a single hourly reading window.
- **Severe Windchill Hazard**: Triggered when `apparent_temperature` < -30.0°C.

## 3. Rationale String Construction Rule
Every generated event must construct its `rationale` column string matching this exact pattern:
`[EVENT_TYPE] | Delta: <calculated_numerical_delta> | Context: <meteorological_significance> | Station: <reporting_city>`
