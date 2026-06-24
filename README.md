# WatchAgent EasyMock Demonstration (Java)

## Overview

This repository contains a focused Java implementation of WatchAgent's meteorological risk assessment engine and an accompanying EasyMock-based test suite.

The original WatchAgent system was developed as a larger weather monitoring and infrastructure risk detection platform. For the purposes of this assignment, the project was intentionally reduced to a small, self-contained Java application that demonstrates:

* Dependency inversion
* Interface-based design
* Unit testing with EasyMock
* Mocked repository interactions
* Business-rule validation independent of infrastructure

The objective of this branch is not to reproduce the entire original system but to provide a clean Java codebase suitable for demonstrating EasyMock testing techniques.

---

# Project Structure

```text
.
├── pom.xml
├── src
│   ├── main
│   │   └── java
│   │       └── com.watchagent
│   │           ├── domain
│   │           │   ├── engine
│   │           │   │   └── RiskAssessmentEngine.java
│   │           │   ├── model
│   │           │   │   ├── Event.java
│   │           │   │   └── WeatherReading.java
│   │           │   └── port
│   │           │       └── WeatherReadingRepository.java
│   └── test
│       └── java
│           └── com.watchagent
│               └── domain
│                   └── engine
│                       └── RiskAssessmentEngineEasyMockTest.java
```

---

# Architecture

The project follows a simple dependency inversion design.

```text
┌──────────────────────────┐
│ RiskAssessmentEngine     │
└─────────────┬────────────┘
              │
              ▼
┌──────────────────────────┐
│ WeatherReadingRepository │
│        Interface         │
└─────────────┬────────────┘
              │
      Mocked by EasyMock
              │
              ▼
┌──────────────────────────┐
│ EasyMock Test Suite      │
└──────────────────────────┘
```

The engine depends only on the repository abstraction and does not know how data is stored or retrieved.

This allows EasyMock to simulate repository responses during testing.

---

# Business Rules Implemented

## Severe Cold Snap (SCS)

Detects prolonged extreme cold conditions.

Thresholds:

| City      | Threshold |
| --------- | --------- |
| Ottawa    | -25°C     |
| Toronto   | -18°C     |
| Vancouver | -5°C      |

Requirements:

* Temperature below city threshold
* Condition must persist for 3 consecutive hours

---

## Flash Freeze

Detects rapid freezing events after precipitation.

Requirements:

* Current temperature below 0°C
* Temperature drop exceeds 5°C within one hour
* Current or prior hour contains precipitation

---

## Corridor Warning

Detects weather systems approaching from upstream regions.

Requirements:

* Target city currently relatively dry
* Windsor or Chicago experiences:

  * Rapid temperature drop, OR
  * Heavy precipitation

Affected cities:

* Toronto
* Ottawa

---

## Pacific Surge

Detects atmospheric river conditions approaching Vancouver.

Requirements:

* Vancouver currently calm
* Tofino reports:

  * Wind > 50 km/h
  * Rain > 15 mm

---

# Technologies

* Java 17
* Maven
* JUnit 5
* EasyMock

---

# Prerequisites

Before building the project, ensure the following are installed:

## Java

Java 17 or newer is required.

Verify:

```bash
java -version
javac -version
```

Expected:

```text
openjdk version "17.x"
javac 17.x
```

---

## Maven

Verify:

```bash
mvn -version
```

Expected output should reference Java 17 or newer.

Example:

```text
Apache Maven 3.x
Java version: 17.x
```

---

# Installing Java 17

## Windows

Install:

* Eclipse Temurin 17
* Amazon Corretto 17
* Oracle JDK 17

After installation:

```cmd
java -version
javac -version
```

---

## macOS

Using Homebrew:

```bash
brew install openjdk@17
```

Verify:

```bash
java -version
```

---

## Ubuntu/Debian

```bash
sudo apt update
sudo apt install openjdk-17-jdk
```

Verify:

```bash
java -version
```

---

## SDKMAN (Optional)

If SDKMAN is installed:

```bash
sdk install java 17.0.19-amzn
sdk use java 17.0.19-amzn
```

Verify:

```bash
java -version
mvn -version
```

---

# Build Instructions

Clone repository:

```bash
git clone <repository-url>
cd watchagent
```

Compile project:

```bash
mvn clean compile
```

Expected:

```text
BUILD SUCCESS
```

---

# Running Tests

Execute:

```bash
mvn clean test
```

Expected output:

```text
Tests run: 8
Failures: 0
Errors: 0
Skipped: 0

BUILD SUCCESS
```

---

# EasyMock Demonstration

The test suite demonstrates:

* Mock creation
* Expected interactions
* Record / Replay / Verify workflow
* Positive scenarios
* Negative scenarios

Example pattern:

```java
WeatherReadingRepository repository =
    createStrictMock(WeatherReadingRepository.class);

expect(repository.findLatestBefore(...))
    .andReturn(Optional.of(reading));

replay(repository);

engine.evaluate(reading);

verify(repository);
```

---

# Test Coverage

Current tests include:

| Rule             | Positive | Negative |
| ---------------- | -------- | -------- |
| Severe Cold Snap | ✓        | ✓        |
| Flash Freeze     | ✓        | ✓        |
| Corridor Warning | ✓        | ✓        |
| Pacific Surge    | ✓        | ✓        |

Total Tests: 8

---

# Design Decisions

The original WatchAgent project included:

* Flask HTTP API
* SQLite persistence
* Weather polling services
* Docker deployment
* Open-Meteo integration

These components were intentionally excluded from this branch because they are unrelated to demonstrating EasyMock.

The assignment focuses on:

* Business logic
* Isolation of dependencies
* Mock-driven testing

---

# Troubleshooting

## Error: invalid target release: 17

Cause:

Maven is using an older JDK.

Check:

```bash
java -version
javac -version
mvn -version
```

Ensure all report Java 17 or newer.

---

## Tests Fail Due to Mock Expectations

Run:

```bash
mvn test
```

Review the specific EasyMock expectation failure.

Most issues are caused by:

* Missing mock expectations
* Unexpected repository calls
* Incorrect replay/verify ordering

---

# Assignment Outcome

This project demonstrates:

* Java object-oriented design
* Dependency inversion
* EasyMock usage
* JUnit testing
* Isolated business-rule validation

All tests currently pass:

```text
Tests run: 8
Failures: 0
Errors: 0
Skipped: 0

BUILD SUCCESS
```
