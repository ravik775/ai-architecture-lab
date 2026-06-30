# Non-Functional Requirements

| Attribute | Target |
|---|---|
| Availability | 99.9% for demo target, 99.95%+ for production |
| Loan Submit Latency | < 300 ms |
| Status Lookup Latency | < 100 ms |
| Scalability | Horizontal scaling for stateless services |
| Reliability | Retries and DLQ for async processing |
| RTO | 30 minutes |
| RPO | 5 minutes with durable database |
| Observability | Logs, metrics, tracing, correlation IDs |
