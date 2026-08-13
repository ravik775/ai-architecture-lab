package org.ex.apigateway.config;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Configuration;

import jakarta.annotation.PostConstruct;

@Configuration
@Slf4j
public class CircuitBreakerEventConfig {

    private final CircuitBreakerRegistry registry;

    public CircuitBreakerEventConfig(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    @PostConstruct
    public void registerListeners() {
        // Covers breakers that already exist at startup...
        registry.getAllCircuitBreakers().forEach(this::addListeners);

        // ...and Resilience4j creates breakers lazily, so one referenced only
        // by an annotation (e.g. paymentCircuitBreaker, created on its first
        // call) would otherwise never get a listener and its state
        // transitions would go unlogged precisely when that telemetry matters.
        registry.getEventPublisher().onEntryAdded(event -> addListeners(event.getAddedEntry()));
    }

    private void addListeners(CircuitBreaker cb) {
        cb.getEventPublisher()
                .onStateTransition(event ->
                        log.info("Circuit Breaker State Changed: {}", event.getStateTransition()));

        cb.getEventPublisher()
                .onError(event ->
                        log.info("Circuit Breaker Error: {}", event.getThrowable().getMessage()));
    }
}