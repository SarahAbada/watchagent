# WatchAgent: Localized & Asymmetric Event Detection Rules

This document defines the deterministic meteorological and infrastructure thresholds for the WatchAgent service. All detection logic must be completely synchronous, deterministic, and calculate risk profiles relative to each target city's unique geographical and infrastructure baseline.

## 1. Upstream Early-Warning Corridor Logic

Detection logic leverages "Upstream Cities" that physically dictate impending weather patterns for target cities due to storm tracks, jet streams, or Pacific maritime surges.

### A. Windsor-Toronto Corridor Warning (Target: Toronto/Ottawa)
- **Logic**: 
  - IF `upstream_city` (Windsor OR Chicago) has a 1-hour temperature drop (`temperature_2m` delta) < -5.0°C OR current hourly `precipitation` > 10.0mm.
  - AND `target_city` (Toronto) current hourly `precipitation` < 2.0mm.
- **Action**: Flag High-Probability Corridor Warning.
- **Mandatory Rationale**: `[CORRIDOR_WARNING] | Delta: Temp Drop or Heavy Rain Upstream | Context: Front moving from Windsor corridor toward Toronto | Station: <upstream_city_name>`

### B. Pacific Atmospheric River Surge (Target: Vancouver)
- **Logic**:
  - IF `upstream_city` (Tofino) `wind_speed_10m` > 50.0 km/h AND current hourly `precipitation` > 15.0mm.
  - AND `target_city` (Vancouver) `wind_speed_10m` < 25.0 km/h.
- **Action**: Flag Atmospheric River Alert.
- **Mandatory Rationale**: `[PACIFIC_SURGE] | Delta: High Wind and Rain Coastline | Context: Pacific storm front detected at Tofino; moving mainland | Station: Tofino`

## 2. Asymmetrical Temperature Shocks (Extreme Heat & Cold)

### A. Severe Cold Snap (SCS)
- **Ottawa**: Triggered when `temperature_2m` < -25.0°C.
  - *Context*: Deep continental Arctic freeze; high risk of residential heating grid overload.
- **Toronto**: Triggered when `temperature_2m` < -18.0°C.
  - *Context*: Extreme urban cold; transit rail switch failures & vulnerable population risk.
- **Vancouver**: Triggered when `temperature_2m` < -5.0°C.
  - *Context*: Maritime climate shock; high risk of shallow-buried residential pipe bursts.

### B. Extreme Heat Wave (EHW)
- **Toronto**: Triggered when `temperature_2m` > 32.0°C.
  - *Context*: High concrete urban heat island effect; subway traction power strain.
- **Ottawa**: Triggered when `temperature_2m` > 30.0°C.
  - *Context*: Continental humidity spike; agricultural stress and electrical grid load.
- **Vancouver**: Triggered when `temperature_2m` > 28.0°C.
  - *Context*: Maritime low tolerance event; extreme risk due to low air-conditioning penetration.

## 3. Localized Infrastructure & Flash Flood Sensitivity

### A. Moderate Flood Risk (MFR)
- **Toronto**: `precipitation` >= 15.0mm in 1 hour. (Concrete pooling and localized urban drainage backups).
- **Ottawa**: `precipitation` >= 20.0mm in 1 hour. (Overwhelmed municipal sewer infrastructure).
- **Vancouver**: `precipitation` >= 30.0mm in 1 hour. (Pacific surge overtaxing coastal gravity drainage systems).

### B. Severe Flood Risk (SFR)
- **Toronto**: `precipitation` >= 25.0mm in 1 hour. (Critical threshold for Don Valley Parkway (DVP) inundation).
- **Ottawa**: `precipitation` >= 35.0mm in 1 hour. (Stalled thunderstorm cells along the valley floor).
- **Vancouver**: `precipitation` >= 50.0mm in 1 hour. (Severe atmospheric river; transit bridge scouring & soil saturation).

## 4. Rationale String Construction Rule
Every generated or calculated event entry written to the database must strictly populate its `rationale` field using this exact tokenized pattern, map the specific municipal asset noted above, and reference the target city:
`[EVENT_TYPE] | Delta: <calculated_numerical_delta> | Context: <city_specific_significance_asset> | Station: <target_city>`
