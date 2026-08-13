package org.ex.oteljaeger.controller;

import org.ex.oteljaeger.model.Order;
import org.ex.oteljaeger.model.OrderRequest;
import org.ex.oteljaeger.service.OrderService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    /**
     * Happy path: produces one trace containing a SERVER span (this request), nested manual
     * spans (validate-order, check-inventory, persist-order) and a CLIENT/SERVER span pair for
     * the loopback call to InventoryController.
     */
    @PostMapping
    public ResponseEntity<Order> createOrder(@RequestBody OrderRequest request) {
        return ResponseEntity.ok(orderService.createOrder(request));
    }

    /**
     * Error path: quantity <= 0 fails validation inside OrderService, which records the
     * exception on its span and marks it ERROR — Jaeger renders this trace with a red span.
     */
    @PostMapping("/invalid-demo")
    public ResponseEntity<Order> createInvalidOrder() {
        return ResponseEntity.ok(orderService.createOrder(new OrderRequest("DEMO-SKU", 0)));
    }
}
