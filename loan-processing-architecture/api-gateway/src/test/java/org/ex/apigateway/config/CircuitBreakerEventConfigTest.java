package org.ex.apigateway.config;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Real CircuitBreakerRegistry, real logging - no mocks. Proves the M2 fix:
 * a circuit breaker created AFTER @PostConstruct ran (the lazy-creation case
 * Resilience4j uses for every breaker referenced only by an annotation, e.g.
 * paymentCircuitBreaker on its first call) still gets a listener and its
 * state transitions still get logged.
 */
class CircuitBreakerEventConfigTest {

    private CircuitBreakerRegistry registry;
    private Logger logger;
    private ListAppender<ILoggingEvent> appender;

    @BeforeEach
    void setUp() {
        registry = CircuitBreakerRegistry.ofDefaults();
        logger = (Logger) LoggerFactory.getLogger(CircuitBreakerEventConfig.class);
        appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
    }

    @AfterEach
    void tearDown() {
        logger.detachAppender(appender);
        appender.stop();
    }

    @Test
    void breakerExistingAtStartup_getsListener_andLogsStateTransition() {
        CircuitBreaker existing = registry.circuitBreaker("loanCircuitBreaker");

        new CircuitBreakerEventConfig(registry).registerListeners();
        existing.transitionToOpenState();

        assertThat(appender.list)
                .extracting(ILoggingEvent::getFormattedMessage)
                .anyMatch(message -> message.contains("Circuit Breaker State Changed"));
    }

    @Test
    void breakerCreatedAfterRegistration_stillGetsListener_viaOnEntryAdded() {
        // This is the exact M2 defect scenario: registerListeners() only used
        // to iterate registry.getAllCircuitBreakers() once at startup, so a
        // breaker Resilience4j creates lazily on its first reference (like
        // paymentCircuitBreaker) got no listener and its transitions went
        // unlogged. onEntryAdded must catch this case too.
        new CircuitBreakerEventConfig(registry).registerListeners();

        CircuitBreaker lazilyCreated = registry.circuitBreaker("paymentCircuitBreaker");
        lazilyCreated.transitionToOpenState();

        assertThat(appender.list)
                .extracting(ILoggingEvent::getFormattedMessage)
                .anyMatch(message -> message.contains("Circuit Breaker State Changed"));
    }

    @Test
    void breakerWithNoListenerRegistration_logsNothing_provingTheAboveAssertionsAreMeaningful() {
        // Control case: without calling registerListeners() at all, a state
        // transition produces no log line. This rules out the possibility
        // that the assertions above pass for an unrelated reason (e.g. some
        // other logger emitting a similarly-worded message).
        CircuitBreaker unmanaged = registry.circuitBreaker("unmanagedBreaker");

        unmanaged.transitionToOpenState();

        assertThat(appender.list)
                .extracting(ILoggingEvent::getFormattedMessage)
                .noneMatch(message -> message.contains("Circuit Breaker State Changed"));
    }
}
