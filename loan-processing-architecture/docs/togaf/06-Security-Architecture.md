# Security Architecture

## Current Demo Scope
Security is intentionally lightweight for laptop execution.

## Production Enhancements
- OAuth2 / OpenID Connect at API Gateway.
- JWT validation.
- RBAC for internal APIs.
- TLS everywhere.
- Secrets in Kubernetes Secrets or Vault.
- Rate limiting at Gateway.
- Audit logging for decision changes.
- PII encryption at rest and in transit.
