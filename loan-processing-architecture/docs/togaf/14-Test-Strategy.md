# Test Strategy

## Test Types
- Unit tests for domain logic.
- Integration tests for RabbitMQ and Redis.
- Contract tests for APIs/events.
- Performance tests for submit/status APIs.
- Chaos tests for Redis/RabbitMQ failure.
- Security tests for authentication and authorization.

## Manual Smoke Test
1. Submit loan through API Gateway.
2. Confirm Redis status exists.
3. Confirm RabbitMQ consumers log event processing.
4. Check status API.
