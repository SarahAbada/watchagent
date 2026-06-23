package com.watchagent.domain.model;

public record Event(
        String city,
        String timestamp,
        String eventType,
        String rationale,
        WeatherReading payloadSnapshot
) {
}
