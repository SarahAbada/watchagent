package com.watchagent.domain.port;

import com.watchagent.domain.model.WeatherReading;

import java.util.List;
import java.util.Optional;

public interface WeatherReadingRepository {
    Optional<WeatherReading> findAtTimestamp(String city, String timestamp);

    Optional<WeatherReading> findLatestBefore(String city, String timestamp);

    List<WeatherReading> findPreceding(String city, String timestamp, int limit);
}
