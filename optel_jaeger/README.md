# otel-jaeger-demo

A deliberately tiny Spring Boot REST API whose only real purpose is to demonstrate
OpenTelemetry tracing end-to-end, visualized in Jaeger. The "business logic" (fake
orders/inventory) exists only as an excuse to generate interesting traces — do not read
anything into the domain model.

## Architecture — Jaeger is a separate server, not part of the app

```
┌─────────────────────────┐   OTLP/HTTP export    ┌──────────────────────┐
│  otel-jaeger-demo        │   (batched POST of     │  Jaeger               │
│  (Spring Boot, port 8091)│──  spans as protobuf) ─▶│  (own container,      │
│  OpenTelemetry SDK        │   :4318/v1/traces      │   UI on :16686)       │
│  builds spans in-process  │                        │  stores + renders     │
└─────────────────────────┘                        └──────────────────────┘
```

Jaeger runs as its own Docker container, with its own ports for the UI (16686) and for
receiving trace data (4317 gRPC / 4318 HTTP). It is not a library linked into the app —
it's a standalone server the app talks to over the network, the same way it would talk to
any other remote service. If Jaeger is down, the app keeps serving HTTP requests fine; it
just fails to export spans (logged, not fatal).

This machine already has a Jaeger container running as part of the sibling
`loan-processing-architecture` docker-compose stack, with 16686/4317/4318 published to the
host. Rather than start a second Jaeger and fight over those ports, `docker-compose.yml`
here only runs the demo app and points it at `host.docker.internal:4318` — whichever Jaeger
is listening on the host picks it up. If you don't already have one running, see
"Standalone Jaeger" below.

## What's actually being demonstrated

| OTel concept | Where |
|---|---|
| Auto-instrumented SERVER spans for every HTTP request | Any controller method, via Spring Boot's Micrometer Tracing auto-config |
| Auto-instrumented CLIENT spans + W3C `traceparent` propagation | `OrderService.createOrder` calling `InventoryController` over real HTTP via `RestClient` |
| Manual spans via the raw `io.opentelemetry.api.trace.Tracer` | `OrderService.validate/persist`, `InventoryController.checkStock` |
| Span attributes | `order.sku`, `order.quantity`, `db.table`, `inventory.stock`, etc. |
| Span events | `validation.passed`, `stock.lookup.started/completed`, `order.persisted` |
| Recorded exceptions + ERROR status | `OrderService.validate` when quantity <= 0 (`POST /api/orders/invalid-demo`) |
| Trace/span ID log correlation | `application.yml` logging pattern includes `%X{traceId}`/`%X{spanId}` |
| OTLP export to Jaeger | `management.otlp.tracing.endpoint` → Jaeger's OTLP/HTTP receiver on port 4318 |
| Sampling configuration | `management.tracing.sampling.probability: 1.0` |

Everything here is real: real Spring Boot app, real OpenTelemetry SDK (via Micrometer
Tracing's OTel bridge), real OTLP export over the network, real Jaeger server. There's no
mocking of telemetry — what you see in the Jaeger UI is exactly what the app produced.

**One honest simplification:** "inventory service" is just a second `@RestController` in
the same JVM, not a separate deployable. `OrderService` still calls it over real HTTP
(loopback to `localhost:8091`), so the CLIENT→SERVER span pair and context propagation are
genuine — it's only the "two microservices" framing that's simulated, to keep this a
single, runnable module instead of two.

## Run it

```bash
docker compose up --build
```

This builds and starts the app on http://localhost:8091, exporting traces to whatever
Jaeger is listening on `host.docker.internal:4318`.

## Generate some traces

```bash
curl -X POST http://localhost:8091/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"WIDGET-1","quantity":3}'

# error path: span recorded with an exception + ERROR status
curl -X POST http://localhost:8091/api/orders/invalid-demo
```

## Look at the trace

Open http://localhost:16686, pick service `otel-jaeger-demo`, click **Find Traces**.
Open a trace from the `POST /api/orders` call and you'll see:

```
POST /api/orders                (SERVER, auto-instrumented)
├─ validate-order                (manual span, attributes: order.sku, order.quantity)
├─ check-inventory                (manual span, wraps the outbound call)
│  └─ GET /api/inventory/{sku}    (CLIENT span, auto-instrumented, propagates traceparent)
│     └─ GET /api/inventory/{sku} (SERVER span, on the receiving side — same trace!)
└─ persist-order                  (manual span, attributes: db.operation, db.table)
```

The `invalid-demo` trace shows `validate-order` rendered in red with the recorded
`IllegalArgumentException` visible in its span details.

## Standalone Jaeger

If nothing is already listening on 4318/16686:

```bash
docker run -d --name jaeger -p 16686:16686 -p 4317:4317 -p 4318:4318 \
  jaegertracing/all-in-one:1.60
```

## Run without Docker (needs a local JDK 17 + Maven)

```bash
mvn spring-boot:run
```
