package com.watchagent.domain.engine;

import com.watchagent.domain.model.Event;
import com.watchagent.domain.model.WeatherReading;
import com.watchagent.domain.port.WeatherReadingRepository;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.function.BiPredicate;

public final class RiskAssessmentEngine {
    private static final Set<String> TARGET_CITIES = Set.of("Ottawa", "Toronto", "Vancouver");
    private static final Set<String> CORRIDOR_TARGETS = Set.of("Toronto", "Ottawa");
    private static final Map<String, Double> SCS_THRESHOLDS = Map.of(
            "Ottawa", -25.0,
            "Toronto", -18.0,
            "Vancouver", -5.0
    );
    private static final Map<String, String> SCS_CONTEXTS = Map.of(
            "Ottawa", "Deep continental Arctic freeze; high risk of residential heating grid overload",
            "Toronto", "Extreme urban cold; transit rail switch failures & vulnerable population risk",
            "Vancouver", "Maritime climate shock; high risk of shallow-buried residential pipe bursts"
    );

    private final WeatherReadingRepository repository;

    public RiskAssessmentEngine(WeatherReadingRepository repository) {
        this.repository = repository;
    }

    public List<Event> evaluate(WeatherReading reading) {
        List<Event> events = new ArrayList<>();
        if (TARGET_CITIES.contains(reading.city())) {
            events.addAll(evaluateSevereColdSnap(reading));
            events.addAll(evaluateFlashFreeze(reading));
            if (CORRIDOR_TARGETS.contains(reading.city())) {
                events.addAll(evaluateCorridorForTarget(reading));
            }
            if ("Vancouver".equals(reading.city())) {
                events.addAll(evaluatePacificSurgeForTarget(reading));
            }
        }
        return events;
    }

    private List<Event> evaluateSevereColdSnap(WeatherReading reading) {
        double threshold = SCS_THRESHOLDS.get(reading.city());
        double temperature = reading.temperature2m();
        if (temperature >= threshold) {
            return List.of();
        }
        if (!threeHourTemperatureStreak(
                reading.city(),
                reading.timestamp(),
                temperature,
                (value, bound) -> value < bound,
                threshold
        )) {
            return List.of();
        }
        String rationale = formatRationale("SCS", String.format("%.1fC", temperature), SCS_CONTEXTS.get(reading.city()), reading.city());
        return List.of(buildEvent(reading.city(), reading.timestamp(), "SCS", rationale, reading));
    }

    private List<Event> evaluateFlashFreeze(WeatherReading reading) {
        if (reading.temperature2m() >= 0.0) {
            return List.of();
        }
        Double tempDelta = oneHourTemperatureDelta(reading);
        if (tempDelta == null || tempDelta >= -5.0) {
            return List.of();
        }

        Optional<WeatherReading> prior = repository.findLatestBefore(reading.city(), reading.timestamp());
        double priorPrecipitation = prior.map(WeatherReading::precipitation).orElse(0.0);
        if (reading.precipitation() <= 0.0 && priorPrecipitation <= 0.0) {
            return List.of();
        }

        String rationale = formatRationale(
                "FLASH_FREEZE",
                String.format("%.1fC drop", tempDelta),
                "Rapid drop below freezing on wet surfaces; extreme ice glaze risk",
                reading.city()
        );
        return List.of(buildEvent(reading.city(), reading.timestamp(), "FLASH_FREEZE", rationale, reading));
    }

    private List<Event> evaluateCorridorForTarget(WeatherReading targetReading) {
        if (targetReading.precipitation() >= 2.0) {
            return List.of();
        }
        List<Event> events = new ArrayList<>();
        for (String upstreamName : List.of("Windsor", "Chicago")) {
            Optional<WeatherReading> upstream = repository.findAtTimestamp(upstreamName, targetReading.timestamp());
            if (upstream.isPresent() && corridorUpstreamTriggered(upstream.get())) {
                events.add(corridorWarningEvent(targetReading.city(), targetReading.timestamp(), upstreamName, targetReading));
            }
        }
        return events;
    }

    private boolean corridorUpstreamTriggered(WeatherReading upstream) {
        Double tempDelta = oneHourTemperatureDelta(upstream);
        if (tempDelta != null && tempDelta < -5.0) {
            return true;
        }
        return upstream.precipitation() > 10.0;
    }

    private Event corridorWarningEvent(String targetCity, String timestamp, String upstreamName, WeatherReading payload) {
        String rationale = formatRationale(
                "CORRIDOR_WARNING",
                "Temp Drop or Heavy Rain Upstream",
                "Front moving from Windsor corridor toward Toronto",
                upstreamName
        );
        return buildEvent(targetCity, timestamp, "CORRIDOR_WARNING", rationale, payload);
    }

    private List<Event> evaluatePacificSurgeForTarget(WeatherReading targetReading) {
        if (targetReading.windSpeed10m() >= 25.0) {
            return List.of();
        }
        Optional<WeatherReading> tofino = repository.findAtTimestamp("Tofino", targetReading.timestamp());
        if (tofino.isEmpty() || !pacificUpstreamTriggered(tofino.get())) {
            return List.of();
        }

        String rationale = formatRationale(
                "PACIFIC_SURGE",
                "High Wind and Rain Coastline",
                "Pacific storm front detected at Tofino; moving mainland",
                "Tofino"
        );
        return List.of(buildEvent("Vancouver", targetReading.timestamp(), "PACIFIC_SURGE", rationale, targetReading));
    }

    private boolean pacificUpstreamTriggered(WeatherReading upstream) {
        return upstream.windSpeed10m() > 50.0 && upstream.precipitation() > 15.0;
    }

    private boolean threeHourTemperatureStreak(
            String city,
            String currentTimestamp,
            double currentTemperature,
            BiPredicate<Double, Double> comparator,
            double threshold
    ) {
        if (!comparator.test(currentTemperature, threshold)) {
            return false;
        }
        List<WeatherReading> preceding = repository.findPreceding(city, currentTimestamp, 2);
        if (preceding.size() < 2) {
            return false;
        }
        return preceding.stream().allMatch(prior -> comparator.test(prior.temperature2m(), threshold));
    }

    private Double oneHourTemperatureDelta(WeatherReading reading) {
        Optional<WeatherReading> prior = repository.findLatestBefore(reading.city(), reading.timestamp());
        return prior.map(weatherReading -> reading.temperature2m() - weatherReading.temperature2m()).orElse(null);
    }

    private String formatRationale(String eventType, String delta, String context, String station) {
        return String.format("[%s] | Delta: %s | Context: %s | Station: %s", eventType, delta, context, station);
    }

    private Event buildEvent(String city, String timestamp, String eventType, String rationale, WeatherReading payload) {
        return new Event(city, timestamp, eventType, rationale, payload);
    }
}
