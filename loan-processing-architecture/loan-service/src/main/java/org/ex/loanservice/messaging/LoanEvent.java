package org.ex.loanservice.messaging;

import java.math.BigDecimal;
import java.time.Instant;

public record LoanEvent(
        String eventType,
        String loanId,
        String tenant,
        String applicantName,
        BigDecimal amount,
        String actor,
        Instant occurredAt
) {
}
