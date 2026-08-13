package org.ex.loanservice.controller;

import org.ex.loanservice.domain.LoanApplication;
import org.ex.loanservice.domain.LoanStatus;

import java.math.BigDecimal;
import java.time.Instant;

public record LoanApplicationResponse(
        String id,
        String applicantName,
        BigDecimal amount,
        String tenant,
        LoanStatus status,
        String submittedBy,
        Instant submittedAt,
        String approvedBy,
        Instant approvedAt
) {
    public static LoanApplicationResponse from(LoanApplication loan) {
        // One snapshot, not three separate getStatus()/getApprovedBy()/getApprovedAt()
        // calls - a concurrent approve() could land between them and the
        // response would mix pre- and post-approval values.
        LoanApplication.ApprovalSnapshot approval = loan.getApproval();
        return new LoanApplicationResponse(
                loan.getId(),
                loan.getApplicantName(),
                loan.getAmount(),
                loan.getTenant(),
                approval.status(),
                loan.getSubmittedBy(),
                loan.getSubmittedAt(),
                approval.approvedBy(),
                approval.approvedAt()
        );
    }
}
