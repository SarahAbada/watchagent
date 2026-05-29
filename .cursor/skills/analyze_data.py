#!/usr/bin/env python3
"""
Cursor Skill: Data Analysis Tool
Queries the persistent SQLite database to calculate trend data, per-city 
comparisons, and verify deduplication compliance.
"""

import sys
import os
import sqlite3
import json

def analyze_database():
    # Enforce priority reading of the environmental database path for Docker persistence parity
    db_path = os.getenv("DATABASE_PATH", "data/weather.db")
    
    if not os.path.exists(db_path):
        return {
            "status": "ERROR",
            "message": f"Database file not found at '{db_path}'. Ensure the poller daemon is running and mounting to the correct data folder."
        }
    
    analysis = {
        "status": "SUCCESS",
        "database_location": db_path,
        "summary": {},
        "city_metrics": [],
        "events_by_type": {},
        "integrity_checks": {}
    }
    
    conn = None
    try:
        # Connect in isolation mode, enabling foreign keys explicitly
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        # 1. Total Core Counts for /health Verification
        cursor.execute("SELECT COUNT(*) FROM weather_readings")
        analysis["summary"]["total_readings_stored"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM notable_events")
        analysis["summary"]["total_events_stored"] = cursor.fetchone()[0]
        
        # 2. Per-City Aggregated Metrics (Using our precise Schema Column names)
        cursor.execute("""
            SELECT 
                city, 
                COUNT(*), 
                MIN(temperature_2m), 
                MAX(temperature_2m), 
                AVG(temperature_2m),
                AVG(precipitation),
                AVG(wind_speed_10m)
            FROM weather_readings 
            GROUP BY city
        """)
        
        for row in cursor.fetchall():
            analysis["city_metrics"].append({
                "city": row[0],
                "total_readings": row[1],
                "min_temp_c": row[2],
                "max_temp_c": row[3],
                "avg_temp_c": round(row[4], 2) if row[4] is not None else 0,
                "avg_precipitation_mm": round(row[5], 2) if row[5] is not None else 0,
                "avg_wind_speed_kmh": round(row[6], 2) if row[6] is not None else 0
            })
            
        # 3. Events Categorized by Event Type
        cursor.execute("SELECT event_type, COUNT(*) FROM notable_events GROUP BY event_type")
        for row in cursor.fetchall():
            analysis["events_by_type"][row[0]] = row[1]
            
        # 4. Strict Deduplication Anomaly Check (Validates rule implementation)
        cursor.execute("""
            SELECT city, timestamp, COUNT(*) 
            FROM weather_readings 
            GROUP BY city, timestamp 
            HAVING COUNT(*) > 1
        """)
        anomalies = cursor.fetchall()
        analysis["integrity_checks"]["deduplication_anomalies_found"] = len(anomalies)
        if len(anomalies) > 0:
            analysis["integrity_checks"]["anomaly_sample"] = [
                {"city": row[0], "timestamp": row[1], "occurrences": row[2]} for row in anomalies[:5]
            ]

    except sqlite3.Error as e:
        return {
            "status": "SQL_ERROR",
            "message": f"Database query execution failed unexpectedly: {str(e)}"
        }
    finally:
        if conn:
            conn.close()
            
    return analysis

if __name__ == "__main__":
    # Safe output parsing for Cursor tools execution
    results = analyze_database()
    print(json.dumps(results, indent=2))
    
    # Exit cleanly with distinct states
    if results.get("status") != "SUCCESS":
        sys.exit(1)
    sys.exit(0)
