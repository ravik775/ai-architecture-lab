# Performance Architecture

## Read Heavy or Write Heavy Classification

| Component | Classification | Reason |
|---|---|---|
| Loan Submission | Write-heavy | Creates application and emits event |
| Loan Status API | Read-heavy | Customers repeatedly check status |
| Credit Score Service | Read-heavy + CPU-bound | Reads customer/credit data and evaluates rules |
| Document Verification | Write-heavy + IO-bound | Validates and stores verification result |
| Notification Service | Async write-heavy | Sends email/SMS/push notification |
| Loan Decision Service | CPU-heavy | Applies business rules and final decision logic |
| Redis | Read-heavy | Serves frequent status queries |
| RabbitMQ | Write/read message throughput | Handles async event fan-out |

## Design Implication
Because status lookup is read-heavy, Redis is used to cache status. Because loan processing is write-heavy and long-running, RabbitMQ decouples consumers and supports independent scaling.
