package org.ex.loanservice.messaging;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

import java.math.BigDecimal;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Verifies the consumer side of the RabbitMQ roundtrip. This listener
 * stands in for what would be a separate notification/disbursement service
 * in a real system, so its observable behavior is its log output - these
 * tests capture that output directly via a Logback test appender rather
 * than just asserting "no exception was thrown".
 */
class LoanNotificationListenerTest {

    private final LoanNotificationListener listener = new LoanNotificationListener();
    private ListAppender<ILoggingEvent> logAppender;
    private Logger listenerLogger;

    @BeforeEach
    void attachLogCapture() {
        listenerLogger = (Logger) LoggerFactory.getLogger(LoanNotificationListener.class);
        logAppender = new ListAppender<>();
        logAppender.start();
        listenerLogger.addAppender(logAppender);
    }

    @AfterEach
    void detachLogCapture() {
        listenerLogger.detachAppender(logAppender);
    }

    private LoanEvent event(String eventType, String actor) {
        return new LoanEvent(eventType, "loan-1", "tenant-a", "Carol Test",
                BigDecimal.valueOf(15000), actor, Instant.now());
    }

    @Test
    void onLoanSubmitted_logsNotificationMentioningLoanIdActorTenantAndAmount() {
        // Scenario: a LOAN_SUBMITTED message arrives on loan.submitted.queue
        // (bound in RabbitMqConfigTest). The listener must log a
        // human-readable notification carrying the loan id, who submitted
        // it, the tenant, and the amount - the pieces a real notification
        // service would need to alert the applicant.
        listener.onLoanSubmitted(event("LOAN_SUBMITTED", "alice-id"));

        assertThat(logAppender.list).hasSize(1);
        String message = logAppender.list.get(0).getFormattedMessage();
        assertThat(message)
                .contains("loan-1")
                .contains("alice-id")
                .contains("tenant-a")
                .contains("15000")
                .containsIgnoringCase("awaiting admin approval");
    }

    @Test
    void onLoanApproved_logsNotificationMentioningApproverAsActor() {
        // Scenario: a LOAN_APPROVED message arrives on loan.approved.queue.
        // The actor here is the approver (bob), not the original
        // submitter - confirms LoanEventPublisher.publishApproved's actor
        // choice actually reaches the consumer correctly.
        listener.onLoanApproved(event("LOAN_APPROVED", "bob-id"));

        assertThat(logAppender.list).hasSize(1);
        String message = logAppender.list.get(0).getFormattedMessage();
        assertThat(message)
                .contains("loan-1")
                .contains("bob-id")
                .containsIgnoringCase("scheduling disbursement");
    }
}
