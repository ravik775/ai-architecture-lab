# ARCHITECTURE & PRODUCTION DESIGN PROMPT: WEATHER APPLICATION (OPEN-METEO)

## 1. ENGINEERING OBJECTIVE & BUSINESS PROBLEM

### 1.1 Business Problem & Context

Users need reliable, real-time, and forecasted weather data based on either their geographic coordinates (latitude/longitude) or human-readable place names (e.g., "Hyderabad", "Tokyo").

### 1.2 Architecture Drivers

* **Functional Drivers:** Geocoding (location search), current weather fetch, hourly/daily forecasts, unit toggles (Celsius/Fahrenheit, km/h/mph), and robust location memory.
* **Operational & NFR Drivers:** Sub-second latency, low infrastructure cost (leveraging Open-Meteo's free non-commercial tier), high reliability against third-party upstream failures, and strict input security.
* **Technology Drivers:** Open-Meteo API requires no API key for non-commercial use, which influences the security posture and authentication layer design.

### 1.3 Alternative Trade-off Matrix

| Option | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| **A. Direct Client-to-OpenMeteo** | Ultra-low operational overhead, zero server cost. | Exposes client IP to 3rd party, lacks server-side caching, rate limit exposure per IP. | **Rejected** |
| **B. Backend Proxy Service (Node.js/Go)** | Hides client, enables server-side caching, centralized rate-limiting, custom metrics. | Minimal server hosting cost required. | **ACCEPTED** |

---

## 2. STAKEHOLDER-DRIVEN DESIGN

* **Primary Users:** End-users seeking fast, hyper-local weather conditions and forecasts.
* **Business Goals:** Provide a reliable weather application with zero user friction (no API key/login forced for basic use) and fast render times ($< 300\text{ ms}$).
* **Success Criteria:** 99.9% uptime for the proxy layer, $<200\text{ ms}$ response latency for cached coordinates, 0 unhandled edge cases during API upstream outages.
* **Known Assumptions:** Open-Meteo API maintains its current non-commercial endpoint stability and schema contracts.
* **Known Risks:** Upstream rate limiting or throttling on Open-Meteo public endpoints during regional weather events.

---

## 3. SIMPLICITY FIRST & CONVENTION OVER REINVENTION

### Architectural Overview

A lightweight API Gateway/Proxy Pattern backed by an in-memory or Redis cache (depending on deployment scale).

```
[ User UI (Web/Mobile) ]
          │
          ▼
┌─────────────────────────────────────────┐
│       App Backend Proxy Service         │
│  (Input Validation, Cache, Resiliency)  │
└──────────────────┬──────────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌──────────────────┐┌──────────────────┐
│ Open-Meteo       ││ Open-Meteo       │
│ Geocoding API    ││ Forecast API     │
└──────────────────┘└──────────────────┘

```

* **No Custom Frameworks:** Standard HTTP/REST, standard schema validation libraries (Zod/Pydantic), standard rate-limiting middleware.

---

## 4. TECHNOLOGY SELECTION EVALUATION

| Component | Selected Technology | Production Maturity | Rationale / Trade-off |
| --- | --- | --- | --- |
| **Geocoding API** | `geocoding-api.open-meteo.com` | High | Directly integrated into Open-Meteo ecosystem; resolves place names to exact lat/long. |
| **Weather API** | `[api.open-meteo.com/v1/forecast](https://api.open-meteo.com/v1/forecast)` | High | Open source, highly scalable, supports WMO weather interpretation codes natively. |
| **Caching Layer** | Redis / In-Memory LRU Cache | High | Reduces upstream calls by ~80% for common cities; respects Open-Meteo caching headers. |
| **HttpClient** | Native Fetch / Axios with Retries | High | Configured with explicit timeouts, connection pooling, and circuit breaker. |

---

## 5. EVIDENCE-BASED ENGINEERING & API VERIFICATION

### 5.1 Verified API Endpoints (via Official Open-Meteo Documentation)

1. **Geocoding Search:**
* **Endpoint:** `GET [https://geocoding-api.open-meteo.com/v1/search?name=](https://geocoding-api.open-meteo.com/v1/search?name=){query}&count=5&language=en&format=json`
* **Verification Status:** Verified via official Open-Meteo API specifications. Returns location details including `latitude`, `longitude`, `country`, and `timezone`.


2. **Weather Forecast Fetch:**
* **Endpoint:** `GET [https://api.open-meteo.com/v1/forecast?latitude=](https://api.open-meteo.com/v1/forecast?latitude=){lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min&timezone=auto`
* **Verification Status:** Verified via official Open-Meteo API specifications. Weather condition mapping relies on official **WMO Weather Interpretation Codes** (e.g., Code 0 = Clear Sky, Code 61 = Slight Rain, Code 95 = Thunderstorm).



---

## 6. PRODUCTION ENGINEERING PRINCIPLES

### 6.1 Performance & Caching Policy

* **Current Weather Data:** Cached for **10 to 15 minutes** (Open-Meteo updates models hourly; 15-minute cache prevents redundant execution while keeping data fresh).
* **Geocoding Data:** Cached for **7 days** (Location coordinates rarely move).

### 6.2 Security

* **Input Sanitization:** Geocoding search inputs must be sanitized against SQLi/XSS/Command Injection. Strictly limit input strings to alphanumeric characters, spaces, and hyphens (`^[a-zA-B0-9\s\-]{2,100}$`).
* **Coordinate Bounds Validation:** Validate latitude ($-90.0 \le \text{lat} \le 90.0$) and longitude ($-180.0 \le \text{lon} \le 180.0$).
* **Out of Scope:** User authentication and PII persistence (not required for standard weather queries).

### 6.3 Observability

* **Structured Logs (JSON):** Capture `trace_id`, `requested_location`, `lat_lon_pair`, `upstream_response_time_ms`, and `cache_hit_status`.
* **Health Endpoints:**
* `/healthz/liveness` (returns `200 OK`)
* `/healthz/readiness` (pings downstream network check or upstream API availability)



### 6.4 Reliability & Resilience

* **Timeouts:** Upstream HTTP calls must strictly timeout at **2000 ms**.
* **Retries:** Exponential backoff retry max 2 attempts on HTTP `5xx` errors. No retries on `4xx` client errors.
* **Fallback Strategy:** If upstream Open-Meteo is unreachable (`503`/Timeout), return stale cached data if available with an added header `X-Data-Stale: true`.

### 6.5 Testability Matrix

* **Unit Tests:** Input validation schema tests, WMO code conversion logic tests.
* **Integration Tests:** Mocked Open-Meteo API HTTP responses for happy path, 400 Bad Request, 429 Too Many Requests, and 500 Server Error scenarios.

---

## 7. AI ENGINEERING PRINCIPLES

### Policy on AI Use in this Application

* **Deterministic Execution:** Weather data retrieval, mathematical unit conversions ($C \to F$), coordinate processing, and WMO code translations are strictly **deterministic**. **No LLMs are used in the core data path.**
* **Optional AI Augmentation (Non-critical Path):** An LLM may be introduced *only* as a secondary, optional capability to generate humanized summary text (e.g., *"It's a chilly morning in Chicago, grab a coat!"*).
* **Safeguards:** If the summary LLM fails or times out (over 500 ms), the application degrades silently and drops the summary, displaying only raw deterministic weather data.

---

## 8. ARCHITECTURE GOVERNANCE & TRACEABILITY

| Business Objective | Requirement | Architecture Decision | Component | Verification |
| --- | --- | --- | --- | --- |
| **Fast Place Search** | Resolve "Tokyo" to weather details under 300 ms | Use Open-Meteo Geocoding + 7-day location cache | `GeocodingService` | Automated integration test + cache hit timing |
| **High System Uptime** | Operate during upstream weather API hiccups | Circuit breaker & stale cache fallback | `ResilienceHandler` | Chaos test (mocking 503 HTTP responses) |
| **Zero Cost Scaling** | Minimal server footprint | Stateless proxy with in-memory caching | `WeatherProxyController` | Load test (1000 req/sec benchmark) |

---

## 9. COMPLETION CRITERIA & LIMITATIONS

### Checklist

* [x] Functional specs (Lat/Lon & Search by Name) defined.
* [x] Verified Open-Meteo API contracts mapped (WMO Codes included).
* [x] Non-functional requirements (Caching, Timeouts, Security, Retries) detailed.
* [x] Deterministic vs. AI execution paths strictly separated.

### Explicitly Stated Limitations

* **Historical Weather:** Historical analysis beyond the standard 7-day forecast requires Open-Meteo's historical API, which is explicitly excluded from this core scope.
* **Commercial Rate Limits:** Free tier is limited to 10,000 call requests/day. If application traffic exceeds this threshold, migration to a paid Open-Meteo tier or commercial provider key will be required.