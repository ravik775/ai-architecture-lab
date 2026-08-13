package org.ex.loanservice.service;

import org.ex.loanservice.domain.LoanStatus;

public class InvalidLoanStateException extends RuntimeException {
    public InvalidLoanStateException(String loanId, LoanStatus actualStatus) {
        super("Loan " + loanId + " cannot be approved from status " + actualStatus);
    }
}
