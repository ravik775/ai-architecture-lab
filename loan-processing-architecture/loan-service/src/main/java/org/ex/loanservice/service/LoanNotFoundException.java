package org.ex.loanservice.service;

public class LoanNotFoundException extends RuntimeException {
    public LoanNotFoundException(String loanId) {
        super("No loan application found with id " + loanId);
    }
}
