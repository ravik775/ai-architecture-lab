package org.ex.apigateway.config;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.context.annotation.Configuration;

import jakarta.annotation.PostConstruct;

@Configuration
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
                            System.out.println(
                                    "Circuit Breaker State Changed: "
                                            + event.getStateTransition()
                            ));

            cb.getEventPublisher()
                    .onError(event ->
                            System.out.println(
                                    "Circuit Breaker Error: "
                                            + event.getThrowable().getMessage()
                            ));
        }
    }
}