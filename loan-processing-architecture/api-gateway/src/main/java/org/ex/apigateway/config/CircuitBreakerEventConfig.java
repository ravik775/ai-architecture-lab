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

        //CircuitBreaker cb = registry.circuitBreaker("loanCircuitBreaker");
        for(var cb : registry.getAllCircuitBreakers()) {
            cb.getEventPublisher()
                    .onStateTransition(event ->
                            log.info("Circuit Breaker State Changed: {}", event.getStateTransition()));

            cb.getEventPublisher()
                    .onError(event ->
                            log.info("Circuit Breaker Error: {}",  event.getThrowable().getMessage() ));
        }
    }
}