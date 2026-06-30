# Architecture Vision

## Problem
Loan processing has multiple independent business capabilities: application intake, credit scoring, document verification, notification, and final decisioning. A synchronous monolith would create tight coupling and poor scalability.

## Target State
A cloud-native microservices architecture using Spring Boot, API Gateway, Eureka, RabbitMQ, Redis, Docker, and Kubernetes.

## Stakeholders
- Customer
- Loan Operations Team
- Credit Risk Team
- Compliance Team
- Platform Engineering Team
- Solution Architect / Enterprise Architect

## Success Criteria
- Submit loan in under 300 ms.
- Retrieve loan status in under 100 ms using cache.
- Services independently deployable.
- Failure isolation between downstream processors.
- Documented tradeoffs through ADRs.
