#!/usr/bin/env python3
"""
Cursor Skill: Replay Simulation Engine
Synchronously queries historical weather records, processes them against
the early-warning meteorological parameters, and tracks signal-to-noise ratios.
"""

import sys
import os
import sqlite3
import json
import logging

LOG_FORMAT = "%(levelname)s | WATCHAGENT_REPLAY | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("ReplaySkill")

class WatchAgentReplay:
    def __init__(self):
        self.db_path = os.getenv("DATABASE_PATH", "data/weather.db")
        if not os.path.exists(self.db_path):
            logger.error(f"[REPLAY_ERROR] Database missing at target path: {self.db_path}")
            raise FileNotFoundError(f"Database missing at {self.db_path}")

    def run_simulation(self):
        results = {
            "status": "SUCCESS",
            "total_readings_processed": 0,
            "events_fired": [],
            "stats": {
                "CORRIDOR_WARNING": 0,
                "THERMAL_TRAP": 0,
                "PACIFIC_SURGE": 0
            }
        }

        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            query = """
                SELECT id, city, timestamp, temperature_2m, apparent_temperature, precipitation, wind_speed_10m, weather_code
                FROM weather_readings 
                ORDER BY timestamp ASC
            """
            cursor.execute(query)
            
            latest_readings = {}
            previous_temps = {} 

            # Process lazily directly from iterator to protect container memory bounds
            for row in cursor:
                reading = {
                    "id": row[0], "city": row[1], "ts": row[2], "temp": row[3],
                    "app_temp": row[4], "precip": row[5], "wind": row[6], "code": row[7]
                }
                
                city = reading["city"]
                results["total_readings_processed"] += 1
                
                last_temp = previous_temps.get(city, reading["temp"])
                temp_delta_1h = reading["temp"] - last_temp
                previous_temps[city] = reading["temp"]
                
                latest_readings[city] = reading

                # 1. Windsor-Toronto Corridor Logic Fix (With strict structural temporal sync checks)
                if city in ["Windsor", "Chicago"]:
                    # Dynamically bind target cross-comparison node based on current context
                    target_station = "Toronto" if city == "Windsor" else "Chicago" # Or keep consistent mapping
                    peer = latest_readings.get("Toronto")
                    
                    # Ensure peer exists AND matches the exact timeline frame window
                    if peer and peer["ts"] == reading["ts"]:
                        if (temp_delta_1h < -5.0 or reading["precip"] > 10.0) and peer["precip"] < 2.0:
                            self._append_event("CORRIDOR_WARNING", reading, f"TempDelta: {temp_delta_1h}C, Precip: {reading['precip']}mm", results)

                # 2. Ottawa Valley Thermal Trap Logic Fix
                if city == "Ottawa":
                    if reading["app_temp"] < 0.0 and reading["precip"] > 2.0 and reading["temp"] > -2.0:
                        self._append_event("THERMAL_TRAP", reading, f"AppTemp: {reading['app_temp']}C, Precip: {reading['precip']}mm", results)

                # 3. Pacific Atmospheric River Surge Logic Fix (With temporal verification)
                if city == "Tofino":
                    vancouver = latest_readings.get("Vancouver")
                    if vancouver and vancouver["ts"] == reading["ts"]:
                        if reading["wind"] > 50.0 and reading["precip"] > 15.0 and vancouver["wind"] < 25.0:
                            self._append_event("PACIFIC_SURGE", reading, f"CoastalWind: {reading['wind']}kmh, Precip: {reading['precip']}mm", results)

            conn.close()
            
            total_events = len(results["events_fired"])
            snr = results["total_readings_processed"] / max(total_events, 1)
            results["signal_to_noise_ratio"] = round(snr, 2)
            
            return results

        except sqlite3.Error as e:
            logger.error(f"[REPLAY_SQL_CRASH] Error: {str(e)}")
            return {"status": "ERROR", "message": str(e)}

    def _append_event(self, event_type, current, metrics_summary, results):
        rationale = f"[{event_type}] | Delta: {metrics_summary} | Context: Early Warning Triggered | Station: {current['city']}"
        
        results["events_fired"].append({
            "type": event_type,
            "city": current["city"],
            "timestamp": current["ts"],
            "rationale": rationale
        })
        results["stats"][event_type] += 1

if __name__ == "__main__":
    replay = WatchAgentReplay()
    sim_data = replay.run_simulation()
    
    sys.stdout.write(json.dumps(sim_data, indent=2) + "\n")
    sys.exit(0)
