# API Gateway: Technical Deep Dive

## Overview
This project implements a robust API Gateway using Spring Cloud Gateway MVC, designed to handle multi-tenant traffic with sophisticated rate limiting and fault tolerance.

## 1. Rate Limiting: The "Lease" Pattern
Unlike standard rate limiters that perform a network roundtrip to Redis for every single request, this implementation uses a **Lease Pattern** to optimize performance.

### Key Components:
- **`TenantLeaseService`**: The core logic provider. It maintains a `ConcurrentHashMap<String, TenantLease>` for local state.
- **`TenantLease`**: Uses an `AtomicLong` for high-concurrency local consumption.
- **Bucket4j + Redis**: The `ProxyManager` interacts with Redis to handle global state.

### The Algorithm:
1. **Fast Path**: When a request arrives, we check the local `TenantLease`. If tokens are available, the request proceeds immediately. This eliminates network latency.
2. **Lease Renewal**: If local tokens are exhausted, the service requests a "lease" (a block of tokens) from Redis.
3. **Synchronization**: The local lease is replenished, and the global bucket is decremented.

**Architectural Benefit:** This significantly reduces the load on Redis and improves response times for high-volume tenants while maintaining global rate enforcement.

---

## 2. Fault Tolerance: Circuit Breaker Strategy
The gateway implements a circuit breaker pattern using **Resilience4j** to prevent cascading failures.

- **Configuration (`application.yml`)**:
    - `slidingWindowSize`: Defined in the config to limit the statistical window of failure.
    - `failureRateThreshold`: Configured (e.g., 50%) to trip the circuit.
    - `fallbackUri`: If the `loan-service` is down, the request is routed to `FallbackController`.

- **Implementation**:
    - The Gateway is configured to forward requests to the `FallbackController` upon a service failure. This allows the API to return a meaningful business error (`LOAN_SERVICE_UNAVAILABLE`) rather than a generic 500 status code.

---

## 3. Technology Stack Analysis
- **Spring Cloud Gateway (MVC)**: Lightweight, servlet-based routing layer.
- **Bucket4j**: Chosen for its fine-grained token-bucket algorithm support.
- **Lettuce**: High-performance Redis client allowing reactive/async interaction.
- **Eureka**: Service discovery, ensuring the Gateway is decoupled from physical service locations.

## 4. Operational Considerations
- **Monitoring**: Actuator endpoints are exposed, providing visibility into the health of the gateway and downstream services.
- **Scalability**: Because the state is managed in Redis (the "Source of Truth"), the Gateway nodes are stateless, allowing for horizontal auto-scaling in Kubernetes or AWS environments.