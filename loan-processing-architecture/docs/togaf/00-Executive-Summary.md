# Executive Summary

This project is a TOGAF 10-inspired enterprise architecture case study for a Loan Processing System. It combines architecture documentation, HLD/LLD, ADRs, capacity planning, NFRs, implementation, and deployment artifacts.

## Business Objective
Provide a scalable loan application platform where customers submit applications, backend services process credit/documents asynchronously, and customers retrieve status quickly.

## Architecture Style
Microservices with hybrid communication:
- Synchronous REST for submit/status APIs.
- Asynchronous RabbitMQ events for long-running processing.
- Redis cache for low-latency loan status lookup.

## Key Outcomes
- Loose coupling through messaging.
- Read-optimized status API using Redis.
- Independently scalable services.
- Laptop-runnable reference architecture.
- Kubernetes-ready deployment manifests.
