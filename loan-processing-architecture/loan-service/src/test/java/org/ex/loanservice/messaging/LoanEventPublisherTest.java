package org.ex.loanservice.messaging;

import org.ex.loanservice.config.RabbitMqConfig;
import org.ex.loanservice.domain.LoanApplication;
import org.ex.loanservice.domain.LoanStatus;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

import java.math.BigDecimal;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

/**
 * Verifies the producer side of the RabbitMQ roundtrip: that submitting or
 * approving a loan results in exactly the right exchange/routing
 * key/payload being handed to RabbitTemplate - independent of whether a
 * real broker is running.
 */
class LoanEventPublisherTest {

    private final RabbitTemplate rabbitTemplate = mock(RabbitTemplate.class);
    private final LoanEventPublisher publisher = new LoanEventPublisher(rabbitTemplate);

    private LoanApplication loan(LoanStatus status, String approvedBy) {
        LoanApplication loan = LoanApplication.builder()
                .id("loan-1")
                .applicantName("Carol Test")
                .amount(BigDecimal.valueOf(15000))
                .tenant("tenant-a")
                .submittedBy("alice-id")
                .submittedAt(Instant.now())
                .build();
        if (status == LoanStatus.APPROVED) {
            loan.tryApprove(approvedBy, Instant.now());
        }
        return loan;
    }

    @Test
    void publishSubmitted_sendsToLoanEventsExchange_withSubmittedRoutingKey() {
        // Scenario: submitting a loan must publish on the "loan.submitted"
        // routing key of the "loan.events" exchange - the exact
        // combination LoanNotificationListener's queue is bound to.
        LoanApplication pending = loan(LoanStatus.PENDING, null);

        publisher.publishSubmitted(pending);

        ArgumentCaptor<LoanEvent> eventCaptor = ArgumentCaptor.forClass(LoanEvent.class);
        verify(rabbitTemplate).convertAndSend(
                eq(RabbitMqConfig.LOAN_EVENTS_EXCHANGE),
                eq(RabbitMqConfig.LOAN_SUBMITTED_ROUTING_KEY),
                eventCaptor.capture());

        LoanEvent event = eventCaptor.getValue();
        assertThat(event.eventType()).isEqualTo("LOAN_SUBMITTED");
        assertThat(event.loanId()).isEqualTo("loan-1");
        assertThat(event.tenant()).isEqualTo("tenant-a");
        assertThat(event.applicantName()).isEqualTo("Carol Test");
        assertThat(event.amount()).isEqualByComparingTo("15000");
        assertThat(event.actor()).isEqualTo("alice-id");
        assertThat(event.occurredAt()).isNotNull();
    }

    @Test
    void publishApproved_sendsToLoanEventsExchange_withApprovedRoutingKey_andApproverAsActor() {
        // Scenario: approving a loan must publish on "loan.approved" and
        // record the *approver* (not the original submitter) as the
        // event's actor - so downstream consumers know who authorized it.
        LoanApplication approved = loan(LoanStatus.APPROVED, "bob-id");

        publisher.publishApproved(approved);

        ArgumentCaptor<LoanEvent> eventCaptor = ArgumentCaptor.forClass(LoanEvent.class);
        verify(rabbitTemplate).convertAndSend(
                eq(RabbitMqConfig.LOAN_EVENTS_EXCHANGE),
                eq(RabbitMqConfig.LOAN_APPROVED_ROUTING_KEY),
                eventCaptor.capture());

        LoanEvent event = eventCaptor.getValue();
        assertThat(event.eventType()).isEqualTo("LOAN_APPROVED");
        assertThat(event.actor()).isEqualTo("bob-id");
    }
}
