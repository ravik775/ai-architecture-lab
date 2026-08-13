package org.ex.loanservice.controller;

import org.ex.loanservice.domain.LoanStatus;
import org.ex.loanservice.service.InvalidLoanStateException;
import org.ex.loanservice.service.LoanNotFoundException;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Pins the HTTP status mapping for the two domain exceptions the service
 * layer throws, independent of MockMvc/servlet plumbing (already exercised
 * end-to-end in LoanControllerSecurityTest's 404/409 cases).
 */
class LoanExceptionHandlerTest {

    private final LoanExceptionHandler handler = new LoanExceptionHandler();

    @Test
    void handleNotFound_mapsLoanNotFoundExceptionTo404_withMessageAsDetail() {
        // Scenario: approving/fetching an unknown loan id must surface as
        // 404 Not Found, carrying the exception's message as the RFC 7807
        // ProblemDetail "detail" so API clients get a readable reason.
        LoanNotFoundException exception = new LoanNotFoundException("missing-id");

        ProblemDetail problem = handler.handleNotFound(exception);

        assertThat(problem.getStatus()).isEqualTo(HttpStatus.NOT_FOUND.value());
        assertThat(problem.getDetail()).contains("missing-id");
    }

    @Test
    void handleInvalidState_mapsInvalidLoanStateExceptionTo409_withMessageAsDetail() {
        // Scenario: re-approving an already-APPROVED loan must surface as
        // 409 Conflict, not 500 - this is what turns the service's atomic
        // state-check failure into the correct HTTP semantics.
        InvalidLoanStateException exception = new InvalidLoanStateException("loan-1", LoanStatus.APPROVED);

        ProblemDetail problem = handler.handleInvalidState(exception);

        assertThat(problem.getStatus()).isEqualTo(HttpStatus.CONFLICT.value());
        assertThat(problem.getDetail()).contains("loan-1").contains("APPROVED");
    }
}
