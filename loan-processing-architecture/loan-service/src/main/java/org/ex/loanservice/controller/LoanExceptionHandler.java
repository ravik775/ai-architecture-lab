package org.ex.loanservice.controller;

import org.ex.loanservice.service.InvalidLoanStateException;
import org.ex.loanservice.service.LoanNotFoundException;
import org.ex.loanservice.service.MissingTenantClaimException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class LoanExceptionHandler {

    @ExceptionHandler(LoanNotFoundException.class)
    ProblemDetail handleNotFound(LoanNotFoundException ex) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, ex.getMessage());
    }

    @ExceptionHandler(InvalidLoanStateException.class)
    ProblemDetail handleInvalidState(InvalidLoanStateException ex) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.CONFLICT, ex.getMessage());
    }

    @ExceptionHandler(MissingTenantClaimException.class)
    ProblemDetail handleMissingTenant(MissingTenantClaimException ex) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.FORBIDDEN, ex.getMessage());
    }
}
