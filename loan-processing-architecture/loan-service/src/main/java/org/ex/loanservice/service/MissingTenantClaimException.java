package org.ex.loanservice.service;

/**
 * loan-service must not trust that api-gateway already rejected tenant-less
 * tokens (see LoanServiceSecurityConfig) - it re-checks independently.
 */
public class MissingTenantClaimException extends RuntimeException {
    public MissingTenantClaimException(String subject) {
        super("JWT for subject '" + subject + "' is missing the required tenant claim");
    }
}
