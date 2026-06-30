# Low-Level Design

## Loan Service
Responsibilities: accept loan applications, cache status, publish event.
Dependencies: Redis, RabbitMQ, Eureka.
APIs: POST /loans, GET /loans/{id}/status.
Failure handling: if Redis fails, production should fallback to database; if RabbitMQ fails, use outbox pattern.

## Credit Score Service
Consumes loan submitted events and evaluates credit score.

## Document Verification Service
Consumes loan submitted events and verifies documents/KYC.

## Notification Service
Consumes loan submitted events and sends customer notification.

## Loan Decision Service
Provides decision endpoint and represents final decision capability.
