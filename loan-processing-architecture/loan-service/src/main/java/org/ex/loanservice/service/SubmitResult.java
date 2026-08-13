package org.ex.loanservice.service;

import org.ex.loanservice.domain.LoanApplication;

/**
 * Outcome of a submit attempt.
 *
 * {@code replayed} distinguishes "this request created the loan" from "an
 * earlier request with the same Idempotency-Key already created it, and this is
 * that same loan". The controller needs the distinction to tell the caller
 * which happened; without it a client retrying after a timeout cannot tell
 * whether it just created a second loan.
 */
public record SubmitResult(LoanApplication loan, boolean replayed) {
}
