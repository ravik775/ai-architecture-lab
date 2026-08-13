package org.ex.loanservice.messaging;

import lombok.extern.slf4j.Slf4j;
import org.ex.loanservice.config.RabbitMqConfig;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

/**
 * Simulates a downstream consumer reacting asynchronously to loan events -
 * standing in for what would be a separate notification/disbursement service
 * in a real system. Demonstrates the producer/consumer roundtrip RabbitMQ
 * was provisioned for but never used (see RabbitMqConfigLogger history).
 */
@Slf4j
@Component
public class LoanNotificationListener {

    @RabbitListener(queues = RabbitMqConfig.LOAN_SUBMITTED_QUEUE)
    public void onLoanSubmitted(LoanEvent event) {
        log.info("Notification: loan {} submitted by {} for tenant {}, amount {} - awaiting admin approval",
                event.loanId(), event.actor(), event.tenant(), event.amount());
    }

    @RabbitListener(queues = RabbitMqConfig.LOAN_APPROVED_QUEUE)
    public void onLoanApproved(LoanEvent event) {
        log.info("Notification: loan {} approved by {} for tenant {}, amount {} - scheduling disbursement",
                event.loanId(), event.actor(), event.tenant(), event.amount());
    }
}
