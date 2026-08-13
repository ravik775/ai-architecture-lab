package org.ex.loanservice.domain;

import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

@Getter
@Builder
public class LoanApplication {
    private final String id;
    private final String applicantName;
    private final BigDecimal amount;
    private final String tenant;
    private final String submittedBy;
    private final Instant submittedAt;

    /**
     * status/approvedBy/approvedAt used to be three independent mutable
     * fields, written together but read independently by get() with no lock
     * and no volatile. A concurrent reader could legally observe
     * status=APPROVED with approvedBy still null - a response claiming
     * approval with no approver. Holding them as one immutable record behind
     * a single AtomicReference means a single approval.get() always returns
     * either the old triple or the new one, never a mix.
     *
     * getStatus()/getApprovedBy()/getApprovedAt() below each still do their
     * own approval.get(), so a caller that invokes two or three of them
     * separately can still observe values from two different points in time
     * (e.g. status from before a concurrent approve(), approvedBy from
     * after it). That is an ordinary "the object changed between two of my
     * reads" race, not a torn field - but any caller that needs a single
     * consistent view of all three (e.g. building an API response) must
     * take one getApproval() snapshot and read all three off it, the way
     * LoanApplicationResponse.from() does.
     */
    @Getter(AccessLevel.NONE)
    @Builder.Default
    private final AtomicReference<ApprovalSnapshot> approval = new AtomicReference<>(ApprovalSnapshot.PENDING);

    public ApprovalSnapshot getApproval() {
        return approval.get();
    }

    public LoanStatus getStatus() {
        return getApproval().status();
    }

    public String getApprovedBy() {
        return getApproval().approvedBy();
    }

    public Instant getApprovedAt() {
        return getApproval().approvedAt();
    }

    /**
     * Atomically transitions PENDING -> APPROVED. Returns false (no change
     * made) if the loan was not PENDING, so the caller can distinguish
     * "already approved / rejected" from success without a separate lock.
     */
    public boolean tryApprove(String approvedBy, Instant approvedAt) {
        return approval.compareAndSet(ApprovalSnapshot.PENDING,
                new ApprovalSnapshot(LoanStatus.APPROVED, approvedBy, approvedAt));
    }

    public record ApprovalSnapshot(LoanStatus status, String approvedBy, Instant approvedAt) {
        static final ApprovalSnapshot PENDING = new ApprovalSnapshot(LoanStatus.PENDING, null, null);
    }
}
