package com.watchagent.domain.engine;

import com.watchagent.domain.model.Event;
import com.watchagent.domain.model.WeatherReading;
import com.watchagent.domain.port.WeatherReadingRepository;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.easymock.EasyMock.createStrictMock;
import static org.easymock.EasyMock.expect;
import static org.easymock.EasyMock.replay;
import static org.easymock.EasyMock.verify;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RiskAssessmentEngineEasyMockTest {

    @Test
    void severeColdSnap_positive() {
        WeatherReadingRepository repository = createStrictMock(WeatherReadingRepository.class);
        RiskAssessmentEngine engine = new RiskAssessmentEngine(repository);

        WeatherReading current = reading("Toronto", "2026-05-28T12:00", -19.0, -21.0, 3.0, 10.0);
        expect(repository.findPreceding("Toronto", "2026-05-28T12:00", 2)).andReturn(List.of(
                reading("Toronto", "2026-05-28T11:00", -20.0, -22.0, 0.0, 10.0),
                reading("Toronto", "2026-05-28T10:00", -20.0, -22.0, 0.0, 10.0)
        ));
        expect(repository.findLatestBefore("Toronto", "2026-05-28T12:00")).andReturn(Optional.empty());

        replay(repository);
        List<Event> events = engine.evaluate(current);
        verify(repository);

        assertEquals(1, events.size());
        assertEquals("SCS", events.get(0).eventType());
    }

    @Test
    void severeColdSnap_negative() {
        WeatherReadingRepository repository = createStrictMock(WeatherReadingRepository.class);
        RiskAssessmentEngine engine = new RiskAssessmentEngine(repository);

        WeatherReading current = reading("Toronto", "2026-05-28T12:00", 5.0, 3.0, 3.0, 10.0);

        replay(repository);
        List<Event> events = engine.evaluate(current);
        verify(repository);

        assertTrue(events.isEmpty());
    }

    @Test
    void flashFreeze_positive() {
        WeatherReadingRepository repository = createStrictMock(WeatherReadingRepository.class);
        RiskAssessmentEngine engine = new RiskAssessmentEngine(repository);

        WeatherReading prior = reading("Vancouver", "2026-05-28T10:00", 5.0, 3.0, 2.0, 12.0);
        WeatherReading current = reading("Vancouver", "2026-05-28T11:00", -1.0, -3.0, 1.5, 30.0);

        expect(repository.findLatestBefore("Vancouver", "2026-05-28T11:00")).andReturn(Optional.of(prior));
        expect(repository.findLatestBefore("Vancouver", "2026-05-28T11:00")).andReturn(Optional.of(prior));

        replay(repository);
        List<Event> events = engine.evaluate(current);
        verify(repository);

        assertEquals(1, events.size());
        assertEquals("FLASH_FREEZE", events.get(0).eventType());
    }

    @Test
    void flashFreeze_negative() {
        WeatherReadingRepository repository = createStrictMock(WeatherReadingRepository.class);
        RiskAssessmentEngine engine = new RiskAssessmentEngine(repository);

        WeatherReading prior = reading("Vancouver", "2026-05-28T10:00", 3.0, 1.0, 2.0, 12.0);
        WeatherReading current = reading("Vancouver", "2026-05-28T11:00", -1.0, -3.0, 1.0, 30.0);

        expect(repository.findLatestBefore("Vancouver", "2026-05-28T11:00")).andReturn(Optional.of(prior));

        replay(repository);
        List<Event> events = engine.evaluate(current);
        verify(repository);

        assertTrue(events.isEmpty());
    }

    @Test
    void corridorWarning_positive() {
        WeatherReadingRepository repository = createStrictMock(WeatherReadingRepository.class);
        RiskAssessmentEngine engine = new RiskAssessmentEngine(repository);

        WeatherReading current = reading("Toronto", "2026-05-28T14:00", 8.0, 6.0, 0.5, 12.0);
        WeatherReading windsor = reading("Windsor", "2026-05-28T14:00", 2.0, 0.0, 12.0, 25.0);
        WeatherReading windsorPrior = reading("Windsor", "2026-05-28T13:00", 10.0, 8.0, 0.0, 15.0);

        expect(repository.findAtTimestamp("Windsor", "2026-05-28T14:00")).andReturn(Optional.of(windsor));
        expect(repository.findLatestBefore("Windsor", "2026-05-28T14:00")).andReturn(Optional.of(windsorPrior));
        expect(repository.findAtTimestamp("Chicago", "2026-05-28T14:00")).andReturn(Optional.empty());

        replay(repository);
        List<Event> events = engine.evaluate(current);
        verify(repository);

        assertEquals(1, events.size());
        assertEquals("CORRIDOR_WARNING", events.get(0).eventType());
        assertEquals("Toronto", events.get(0).city());
    }

    @Test
    void corridorWarning_negative() {
        WeatherReadingRepository repository = createStrictMock(WeatherReadingRepository.class);
        RiskAssessmentEngine engine = new RiskAssessmentEngine(repository);

        WeatherReading current = reading("Toronto", "2026-05-28T14:00", 8.0, 6.0, 2.5, 12.0);

        replay(repository);
        List<Event> events = engine.evaluate(current);
        verify(repository);

        assertTrue(events.isEmpty());
    }

    @Test
    void pacificSurge_positive() {
        WeatherReadingRepository repository = createStrictMock(WeatherReadingRepository.class);
        RiskAssessmentEngine engine = new RiskAssessmentEngine(repository);

        WeatherReading current = reading("Vancouver", "2026-05-28T14:00", 8.0, 6.0, 1.0, 20.0);
        WeatherReading tofino = reading("Tofino", "2026-05-28T14:00", 7.0, 5.0, 20.0, 55.0);

        expect(repository.findAtTimestamp("Tofino", "2026-05-28T14:00")).andReturn(Optional.of(tofino));

        replay(repository);
        List<Event> events = engine.evaluate(current);
        verify(repository);

        assertEquals(1, events.size());
        assertEquals("PACIFIC_SURGE", events.get(0).eventType());
    }

    @Test
    void pacificSurge_negative() {
        WeatherReadingRepository repository = createStrictMock(WeatherReadingRepository.class);
        RiskAssessmentEngine engine = new RiskAssessmentEngine(repository);

        WeatherReading current = reading("Vancouver", "2026-05-28T14:00", 8.0, 6.0, 1.0, 26.0);

        replay(repository);
        List<Event> events = engine.evaluate(current);
        verify(repository);

        assertTrue(events.isEmpty());
    }

    private static WeatherReading reading(
            String city,
            String timestamp,
            double temperature2m,
            double apparentTemperature,
            double precipitation,
            double windSpeed10m
    ) {
        return new WeatherReading(city, timestamp, temperature2m, apparentTemperature, precipitation, windSpeed10m, 0);
    }
}
