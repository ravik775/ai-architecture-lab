Here's the consolidated plan, phase by phase, cross-checked line-by-line against the actual repo (not the abstract design) — I've flagged anywhere my earlier assumption needs correcting after re-reading the source.

## Verification pass first (a few corrections to what I said earlier)

- Confirmed: `management.endpoints.web.exposure.include: "*"` is real, in `api-gateway/src/main/resources/application.yml`.
- Confirmed: Redis has no `requirepass` anywhere — `docker-compose.yml`'s redis service has no auth env var, and `LettuceConfig`/`application.yml` connect with no password.
- Confirmed: RabbitMQ creds (`admin`/`admin123`) are plaintext in `docker-compose.yml`, and `loan-service/application.yml` duplicates them in plaintext too.
- Confirmed: RabbitMQ is genuinely unused — `loan-service/pom.xml` declares `spring-boot-starter-amqp` and `application.yml` has `spring.rabbitmq.*` config, but there is **no `@RabbitListener`, no `RabbitTemplate` usage, no queue/exchange bean anywhere in the codebase**. It's provisioned infrastructure, zero consumers. This makes it a genuinely free target for the SCIM-event and control-plane work — nothing to migrate away from.
- Confirmed: the gateway is on `spring-cloud-starter-gateway-server-webmvc` (servlet stack) — routes live under `spring.cloud.gateway.mvc.routes` in `application.yml`, and `TenantFilterFunctions` uses `HandlerFilterFunction<ServerResponse, ServerResponse>` — this is MVC-specific, confirming Phase 0 is a real rewrite, not a relabeling.
- Confirmed: `TenantPolicyService.getPolicy()` only reads (`template.opsForValue().get(key)`, falling back to `getDefault()`) — there is no setter/write path anywhere, so the control-plane gap I described is real, not speculative.
- Confirmed: `TenantFilterFunctions.tenantRateLimiter()` reads `request.headers().firstHeader("X-Tenant-Id")` directly with no signature/claim verification — this is the exploitable spoofing vector.

## Phased Plan

**Phase 0 — Reactive gateway conversion**
- `pom.xml`: `...-gateway-server-webmvc` → `...-gateway-server-webflux`; `...-circuitbreaker-resilience4j` → `...-circuitbreaker-reactor-resilience4j`
- `TenantFilterFunctions.java` → rewritten as a `GlobalFilter` returning `Mono<Void>`
- `TenantLeaseService.java` → Bucket4j async CAS via `.asAsync()` + `Mono.fromFuture(...)`
- `LettuceConfig.java` / `Bucket4jRedisConfiguration.java` → async-capable proxy manager
- `GatewayRouteLogger.java` → reactive route introspection API
- `application.yml` → `spring.cloud.gateway.mvc.routes` → `spring.cloud.gateway.routes`
- `TenantRateLimiterConfiguration.java` → `SimpleFilterSupplier` (MVC-only) replaced with `GlobalFilter` bean
- *Blocks Phase 2* (security config written once, reactive-native)

**Phase 1 — Close current exploitable gaps** *(independent, do regardless of sequencing above)*
- `application.yml`: `management.endpoints.web.exposure.include` → `health,info,prometheus`
- `docker-compose.yml` + both `application.yml` files: externalize Redis/RabbitMQ creds to `.env` (gitignored), add Redis `requirepass`
- Add actor/correlation-ID fields to existing `log.info`/`log.debug` calls in `TenantLeaseService`, `TenantPolicyService`

**Phase 2 — OAuth2/OIDC resource server**
- Add Keycloak to `docker-compose.yml`, realm export with roles + `tenant` attribute/claim
- New `SecurityConfig.java` (reactive `SecurityWebFilterChain`) in `api-gateway`
- Rewrite `TenantFilterFunctions` to derive tenant from the verified JWT claim, not the header — closes the spoofing vector from Phase 1's threat model
- `loan-service` becomes its own resource server too (independent JWT re-validation — zero-trust internally, per the "gateway bypass" STRIDE finding)

**Phase 3 — RBAC + SoD + SCIM adapter (event-driven)**
- Route/method-level `@PreAuthorize` in both `api-gateway` and `loan-service`
- New `scim-adapter` module: SCIM 2.0 REST endpoints → Keycloak Admin REST API (sync response)
- SoD conflict check runs inside the adapter before the Keycloak call — rejects `409` on conflicting role assignment, no event published on rejection
- On successful mutation, publish `UserProvisioned` / `UserRoleChanged` / `UserDeactivated` to RabbitMQ — **first real consumer of the already-provisioned, currently-idle RabbitMQ**
- JWT propagation: forward `Authorization` header unmodified gateway → `loan-service` (Option A from earlier); `loan-service` validates independently

**Phase 4 — SPIFFE/SPIRE**
- Real SPIRE server + agent in `docker-compose.yml`
- Workload attestation, SVIDs for `api-gateway` and `loan-service`
- mTLS between gateway and services; internal header context (Option C) becomes trustworthy once it rides an SVID-authenticated channel

**Phase 5 — SAML federation demo**
- Keycloak as SAML SP brokering an external/mock SAML IdP, re-issuing OIDC tokens downstream
- Lowest priority unless the rubric specifically weighs it

**Phase 6 — CI/CD**
- The pipeline already delivered (`ci-cd-pipeline.yml`): Semgrep + SonarQube (SAST) → OWASP Dependency-Check + Trivy (SCA/image) → OWASP ZAP (DAST, post-merge against a live compose stack)
- Runs in parallel with all phases above; not blocking

**Phase 6.5 — RabbitMQ-backed control plane** *(stretch, strengthens the "event-based, multi-region" claim)*
- Admin API (`PUT /admin/tenants/{id}/policy`) giving `TenantPolicyService` its missing write path
- Publish `TenantPolicyChanged` to RabbitMQ (via Spring Cloud Bus) so every gateway replica/region invalidates cache instead of hitting Redis per-request
- Reuses the same event bus stood up in Phase 3 — one integration, two purposes

Want me to start writing Phase 0's actual diff now, or do you want to reorder/drop anything first (e.g. push Phase 4 SPIFFE below Phase 6.5, since the control-plane story might matter more for your rubric than mTLS)?