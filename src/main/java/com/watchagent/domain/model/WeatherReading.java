package com.watchagent.domain.model;

public record WeatherReading(
        String city,
        String timestamp,
        double temperature2m,
        double apparentTemperature,
        double precipitation,
        double windSpeed10m,
        int weatherCode
) {
}
