# Architecture Decision Records

## ADR-001: Use RabbitMQ for Asynchronous Processing
Alternatives: Kafka, AWS SQS, synchronous REST.
Decision: RabbitMQ.
Reason: simple routing, queue semantics, retry/DLQ support, easy laptop execution.

## ADR-002: Use Redis for Loan Status Cache
Alternatives: database-only reads, Hazelcast, Caffeine local cache.
Decision: Redis.
Reason: shared distributed cache, fast reads, reduces database load.

## ADR-003: Use Spring Cloud Gateway
Alternatives: NGINX, Kong, AWS API Gateway.
Decision: Spring Cloud Gateway for demo.
Reason: simple Java/Spring integration and service discovery support.

## ADR-004: Use Eureka for Service Discovery
Alternatives: Kubernetes DNS, Consul.
Decision: Eureka for local microservice demonstration.
Reason: easy to demonstrate discovery on laptop; in Kubernetes, DNS/service discovery can replace Eureka.
