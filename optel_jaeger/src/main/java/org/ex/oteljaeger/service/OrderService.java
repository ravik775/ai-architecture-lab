package org.ex.oteljaeger.service;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.ex.oteljaeger.model.Order;
import org.ex.oteljaeger.model.OrderRequest;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Deliberately calls the OpenTelemetry API directly (rather than Micrometer's Tracer facade)
 * to make the manual-instrumentation pattern explicit: spans, attributes, events and error
 * status all come straight from io.opentelemetry.api.
 */
@Service
public class OrderService {

    private final Tracer tracer;
    private final RestClient inventoryRestClient;

    public OrderService(OpenTelemetry openTelemetry, RestClient inventoryRestClient) {
        this.tracer = openTelemetry.getTracer(OrderService.class.getName());
        this.inventoryRestClient = inventoryRestClient;
    }

    public Order createOrder(OrderRequest request) {
        validate(request);

        // No explicit parent is set, so this span attaches to whatever span is active on the
        // current thread — here, the SERVER span Spring created for the incoming HTTP request.
        Span checkStockSpan = tracer.spanBuilder("check-inventory")
                .setAttribute("order.sku", request.sku())
                .startSpan();
        Map<?, ?> stock;
        try (Scope scope = checkStockSpan.makeCurrent()) {
            // This call goes out over real HTTP to InventoryController. Spring's auto-instrumentation
            // opens a CLIENT span here and injects a traceparent header so the two processes' spans
            // (client call + server handling) land in the same trace.
            stock = inventoryRestClient.get()
                    .uri("/api/inventory/{sku}", request.sku())
                    .retrieve()
                    .body(Map.class);
            checkStockSpan.addEvent("inventory.response.received");
        } finally {
            checkStockSpan.end();
        }

        Order order = persist(request);
        checkStockSpan.setAttribute("inventory.snapshot", String.valueOf(stock));
        return order;
    }

    private void validate(OrderRequest request) {
        Span span = tracer.spanBuilder("validate-order")
                .setAttribute("order.sku", request.sku())
                .setAttribute("order.quantity", request.quantity())
                .startSpan();
        try (Scope scope = span.makeCurrent()) {
            if (request.quantity() <= 0) {
                IllegalArgumentException error = new IllegalArgumentException("quantity must be positive");
                span.recordException(error);
                span.setStatus(StatusCode.ERROR, "invalid quantity");
                throw error;
            }
            span.addEvent("validation.passed");
        } finally {
            span.end();
        }
    }

    private Order persist(OrderRequest request) {
        Span span = tracer.spanBuilder("persist-order")
                .setAttribute("db.operation", "INSERT")
                .setAttribute("db.table", "orders")
                .startSpan();
        try (Scope scope = span.makeCurrent()) {
            // Simulated write latency so the span has a realistic, non-zero duration in Jaeger.
            Thread.sleep(ThreadLocalRandom.current().nextInt(10, 60));
            String id = UUID.randomUUID().toString();
            span.setAttribute("order.id", id);
            span.addEvent("order.persisted", Attributes.of(
                    io.opentelemetry.api.common.AttributeKey.stringKey("order.id"), id));
            return new Order(id, request.sku(), request.quantity(), "CREATED");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException(e);
        } finally {
            span.end();
        }
    }
}
