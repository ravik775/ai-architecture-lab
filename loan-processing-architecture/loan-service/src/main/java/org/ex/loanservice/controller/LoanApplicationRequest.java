package org.ex.loanservice.controller;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;

public record LoanApplicationRequest(
        @NotBlank String applicantName,
        @NotNull @DecimalMin(value = "0.01") BigDecimal amount
) {
}
