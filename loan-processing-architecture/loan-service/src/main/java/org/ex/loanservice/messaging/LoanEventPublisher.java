package org.ex.loanservice.messaging;

import lombok.RequiredArgsConstructor;
import org.ex.loanservice.config.RabbitMqConfig;
import org.ex.loanservice.domain.LoanApplication;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Component
@RequiredArgsConstructor
public class LoanEventPublisher {

    private final RabbitTemplate rabbitTemplate;

    public void publishSubmitted(LoanApplication loan) {
        publish(RabbitMqConfig.LOAN_SUBMITTED_ROUTING_KEY, "LOAN_SUBMITTED", loan, loan.getSubmittedBy());
    }

    public void publishApproved(LoanApplication loan) {
        publish(RabbitMqConfig.LOAN_APPROVED_ROUTING_KEY, "LOAN_APPROVED", loan, loan.getApprovedBy());
    }

    private void publish(String routingKey, String eventType, LoanApplication loan, String actor) {
        LoanEvent event = new LoanEvent(
                eventType,
                loan.getId(),
                loan.getTenant(),
                loan.getApplicantName(),
                loan.getAmount(),
                actor,
                Instant.now()
        );
        rabbitTemplate.convertAndSend(RabbitMqConfig.LOAN_EVENTS_EXCHANGE, routingKey, event);
    }
}
