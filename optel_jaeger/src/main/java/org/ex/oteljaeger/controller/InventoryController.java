package org.ex.oteljaeger.controller;

import io.opentelemetry.api.trace.Span;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

/**
 * Stands in for a separate "inventory service". It lives in the same process purely to
 * keep this demo to a single deployable, but the call into it from OrderService is a real
 * HTTP request, so it produces a real CLIENT/SERVER span pair with trace context propagated
 * over the wire via the W3C traceparent header.
 */
@RestController
public class InventoryController {

    @GetMapping("/api/inventory/{sku}")
    public Map<String, Object> checkStock(@PathVariable String sku) {
        Span currentSpan = Span.current();
        currentSpan.setAttribute("inventory.sku", sku);

        // Simulate a variable-latency lookup (e.g. a warehouse DB call) so traces show
        // realistic, non-uniform span durations in the Jaeger timeline.
        int latencyMs = ThreadLocalRandom.current().nextInt(20, 150);
        currentSpan.addEvent("stock.lookup.started");
        try {
            Thread.sleep(latencyMs);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        int stock = ThreadLocalRandom.current().nextInt(0, 50);
        currentSpan.setAttribute("inventory.stock", stock);
        currentSpan.addEvent("stock.lookup.completed");

        return Map.of("sku", sku, "inStock", stock, "latencyMs", latencyMs);
    }
}
