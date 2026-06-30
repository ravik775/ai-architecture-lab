# Application Architecture

## Services
| Service | Responsibility | Type |
|---|---|---|
| API Gateway | Routes external traffic | Edge service |
| Service Registry | Service discovery | Platform service |
| Loan Service | Submit loan, retrieve status | Core domain service |
| Credit Score Service | Evaluate credit profile | Domain service |
| Document Verification Service | Validate documents/KYC | Domain service |
| Notification Service | Notify customer | Supporting service |
| Loan Decision Service | Final decision endpoint | Domain service |

## Communication
- REST: Client -> Gateway -> Loan Service.
- Messaging: Loan Service -> RabbitMQ -> Consumers.
- Cache: Loan Service -> Redis.

## API
### Submit Loan
`POST /loans`

### Check Loan Status
`GET /loans/{applicationId}/status`
