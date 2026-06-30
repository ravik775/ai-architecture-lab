Below is project-ready Markdown.


# Resilience Patterns in Loan Processing Microservices

This document explains where to implement Rate Limiter, Retry, Circuit Breaker, Bulkhead, and Load Balancer in a real production microservices system.

## 1. Where Should Rate Limiter Be Implemented?

### Short Answer

Rate limiting should usually be implemented at the **API Gateway**.

Service-level rate limiting can also be added for highly sensitive services.

## 2. Gateway vs Service Responsibility

| Pattern | Gateway | Service |
|---|---|---|
| Rate Limiter | Recommended | Optional |
| Retry | Recommended for GET/read calls | Recommended for outbound service calls |
| Circuit Breaker | Recommended per downstream route | Recommended for service-to-service calls |
| Bulkhead | Limited use | Strongly recommended |
| Load Balancer | Recommended | Used through service discovery/client |

## 3. Rate Limiter

Rate Limiter controls how many requests a client can send in a given time.

Example:


User A can call Loan API 10 times per second.
If User A exceeds this limit, Gateway returns HTTP 429.


Spring Cloud Gateway provides `RequestRateLimiter`; if a request is not allowed, it returns `HTTP 429 Too Many Requests`. ([Home][1])

### Gateway Rate Limiter Example

```yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: loan-service
              uri: lb://LOAN-SERVICE
              predicates:
                - Path=/loan/**
              filters:
                - StripPrefix=1
                - name: RequestRateLimiter
                  args:
                    redis-rate-limiter.replenishRate: 10
                    redis-rate-limiter.burstCapacity: 20
                    key-resolver: "#{@userKeyResolver}"
```

### Where It Helps

```text
Client
  |
  | Too many requests
  v
API Gateway
  |
  | Blocks excessive traffic
  v
Loan Service
```

### Production Recommendation

Use Gateway rate limiting for:

* API abuse protection
* Tenant-level quotas
* User-level quotas
* IP-based throttling
* Public API protection

Use service-level rate limiting when:

* A specific service is expensive
* A service calls paid external APIs
* A service must protect its own database

## 4. Retry

Retry is used when a failure may be temporary.

Example:

```text
Loan Service returns 503.
Gateway waits 100ms and retries.
```

### Gateway Retry Example

```yaml
filters:
  - name: Retry
    args:
      retries: 3
      statuses:
        - BAD_GATEWAY
        - SERVICE_UNAVAILABLE
        - GATEWAY_TIMEOUT
      methods:
        - GET
      backoff:
        firstBackoff: 100ms
        maxBackoff: 1s
        factor: 2
        basedOnPreviousValue: false
```

### Important Production Rule

Do not blindly retry `POST`, `PUT`, or payment/loan submission APIs.

Bad example:

```text
POST /loan/apply
```

If retried automatically, it may create duplicate loan applications.

Retry `POST` only when the API supports idempotency.

Example:

```http
Idempotency-Key: APP-123456
```

## 5. Circuit Breaker

Circuit Breaker stops calls to a failing service.

Example:

```text
Loan Service is failing continuously.
Circuit Breaker opens.
Gateway stops calling Loan Service temporarily.
Fallback response is returned.
```

Resilience4j supports CircuitBreaker, Retry, RateLimiter, Bulkhead, and TimeLimiter configuration through Spring Boot `application.yml`. ([resilience4j][2])

### Gateway Circuit Breaker Example

```yaml
filters:
  - name: CircuitBreaker
    args:
      name: loanCircuitBreaker
      fallbackUri: forward:/fallback/loan-service
```

### Resilience4j Configuration

```yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowSize: 20
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5

    instances:
      loanCircuitBreaker:
        baseConfig: default
```

### Flow

```text
Client
  |
  v
API Gateway
  |
  v
Circuit Breaker
  |
  | Service healthy
  v
Loan Service

If service fails repeatedly:

Client
  |
  v
API Gateway
  |
  v
Fallback Response
```

## 6. Bulkhead

Bulkhead limits how many concurrent calls can enter a section of the system.

It prevents one slow dependency from consuming all application threads.

### Real Production Implementation

In real production, Bulkhead is usually implemented **inside services**, not only at the Gateway.

Example:

```text
Loan Service calls:
- Credit Score Service
- Document Verification Service
- Notification Service
```

If Credit Score Service becomes slow, it should not consume all Loan Service threads.

### Service-Level Bulkhead Example

```yaml
resilience4j:
  bulkhead:
    instances:
      creditScoreBulkhead:
        maxConcurrentCalls: 10
        maxWaitDuration: 0

      documentVerificationBulkhead:
        maxConcurrentCalls: 20
        maxWaitDuration: 100ms
```

### Java Example

```java
@Service
public class CreditScoreClient {

    @Bulkhead(name = "creditScoreBulkhead", fallbackMethod = "creditScoreFallback")
    @CircuitBreaker(name = "creditScoreCircuitBreaker", fallbackMethod = "creditScoreFallback")
    @Retry(name = "creditScoreRetry", fallbackMethod = "creditScoreFallback")
    public CreditScoreResponse getCreditScore(String customerId) {
        // REST call to Credit Score Service
        return restClient.get()
                .uri("/credit-score/{customerId}", customerId)
                .retrieve()
                .body(CreditScoreResponse.class);
    }

    public CreditScoreResponse creditScoreFallback(String customerId, Exception ex) {
        return new CreditScoreResponse(customerId, 0, "CREDIT_SCORE_UNAVAILABLE");
    }
}
```

## 7. Circuit Breaker + Bulkhead Together

They solve different problems.

| Pattern         | Purpose                                      |
| --------------- | -------------------------------------------- |
| Circuit Breaker | Stops calling a failing service              |
| Bulkhead        | Limits concurrent calls to protect resources |
| Retry           | Handles temporary failures                   |
| Rate Limiter    | Controls request volume                      |
| Load Balancer   | Distributes traffic across service instances |

### Combined Example

```text
Loan Service
  |
  | Bulkhead: only 10 concurrent calls
  |
  | Circuit Breaker: open if 50% fail
  |
  | Retry: retry temporary failures
  v
Credit Score Service
```

## 8. How Load Balancer Helps When Bulkhead Blocks a Service

Assume there are 3 Loan Service instances.

```text
LOAN-SERVICE
  - loan-service-1
  - loan-service-2
  - loan-service-3
```

Gateway route:

```yaml
uri: lb://LOAN-SERVICE
```

Spring Cloud Gateway uses `lb://service-name` to resolve a service name to an actual host and port through Spring Cloud LoadBalancer. ([Home][3])

### Example Scenario

Each Loan Service instance has a Bulkhead limit:

```text
maxConcurrentCalls = 10
```

So total capacity is:

```text
loan-service-1 = 10 concurrent calls
loan-service-2 = 10 concurrent calls
loan-service-3 = 10 concurrent calls

Total = 30 concurrent calls
```

### Request Flow

```text
Client Requests
      |
      v
API Gateway
      |
      v
Load Balancer
      |
      +--> loan-service-1
      +--> loan-service-2
      +--> loan-service-3
```

If `loan-service-1` reaches its Bulkhead limit:

```text
loan-service-1 = full
loan-service-2 = available
loan-service-3 = available
```

The Load Balancer can still send new requests to the other available instances.

### Important Note

The Load Balancer does not directly know that a Bulkhead is full unless health checks, failures, or response behavior reveal it.

So production systems usually combine:

```text
Load Balancer
+ Health Checks
+ Circuit Breaker
+ Bulkhead
+ Metrics
+ Auto Scaling
```

## 9. Gateway-Level Example

```yaml
spring:
  application:
    name: api-gateway

  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: loan-service
              uri: lb://LOAN-SERVICE
              predicates:
                - Path=/loan/**
              filters:
                - StripPrefix=1

                - name: Retry
                  args:
                    retries: 3
                    statuses:
                      - BAD_GATEWAY
                      - SERVICE_UNAVAILABLE
                      - GATEWAY_TIMEOUT
                    methods:
                      - GET
                    backoff:
                      firstBackoff: 100ms
                      maxBackoff: 1s
                      factor: 2
                      basedOnPreviousValue: false

                - name: CircuitBreaker
                  args:
                    name: loanCircuitBreaker
                    fallbackUri: forward:/fallback/loan-service
```

## 10. Service-Level Resilience4j Example

```yaml
resilience4j:
  circuitbreaker:
    instances:
      creditScoreCircuitBreaker:
        slidingWindowSize: 20
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5

  retry:
    instances:
      creditScoreRetry:
        maxAttempts: 3
        waitDuration: 500ms

  bulkhead:
    instances:
      creditScoreBulkhead:
        maxConcurrentCalls: 10
        maxWaitDuration: 0

  ratelimiter:
    instances:
      creditScoreRateLimiter:
        limitForPeriod: 50
        limitRefreshPeriod: 1s
        timeoutDuration: 0
```

## 11. Recommended Production Placement

### API Gateway

Implement:

```text
Rate Limiter
Retry for safe methods
Circuit Breaker per downstream service
Authentication and authorization
Routing
Request/response logging
```

### Services

Implement:

```text
Circuit Breaker for outbound calls
Bulkhead for expensive dependencies
Retry for transient downstream failures
Timeout for all remote calls
Rate Limiter for expensive internal operations
```

## 12. Loan Processing Example

```text
Client
  |
  v
API Gateway
  |
  | Rate Limiter
  | Retry
  | Circuit Breaker
  | Load Balancer
  v
Loan Service
  |
  | Bulkhead + Circuit Breaker + Retry
  v
Credit Score Service

Loan Service
  |
  | Bulkhead + Circuit Breaker
  v
Document Verification Service

Loan Service
  |
  | Bulkhead
  v
Notification Service
```

## 13. Best Practice Summary

| Requirement                      | Recommended Pattern             |
| -------------------------------- | ------------------------------- |
| Stop abusive clients             | Gateway Rate Limiter            |
| Handle temporary 503/504 errors  | Retry                           |
| Stop calling failed services     | Circuit Breaker                 |
| Prevent thread exhaustion        | Bulkhead                        |
| Distribute load across instances | Load Balancer                   |
| Avoid duplicate POST processing  | Idempotency Key                 |
| Protect external paid APIs       | Service Rate Limiter + Bulkhead |
| Protect database calls           | Bulkhead + Timeout              |

## 14. Interview Summary

In production, rate limiting is usually implemented at the API Gateway to protect the platform from abusive or excessive traffic before it reaches backend services. Circuit breakers are implemented both at the Gateway and service level to stop repeated calls to failing dependencies. Bulkheads are mainly implemented inside services to isolate resources and prevent one slow dependency from exhausting all application threads. Retry is used only for transient failures and mostly for idempotent operations. Load balancing distributes traffic across healthy service instances, and when one instance is saturated or failing, other instances can continue serving requests.

```
```

[1]: https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html?utm_source=chatgpt.com "RequestRateLimiter GatewayFilter Factory"
[2]: https://resilience4j.readme.io/docs/getting-started-3?utm_source=chatgpt.com "Getting Started - resilience4j - ReadMe"
[3]: https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/loadbalancer.html?utm_source=chatgpt.com "LoadBalancer Filter :: Spring Cloud Gateway"
