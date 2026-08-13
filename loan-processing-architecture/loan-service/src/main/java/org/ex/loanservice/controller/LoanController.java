package org.ex.loanservice.controller;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.ex.loanservice.service.LoanApplicationService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Demonstrates OIDC role-based authorization: submitting a loan requires the
 * "loan-officer" realm role, approving it requires "loan-admin". Both roles
 * come from the verified JWT's "roles" claim (see LoanServiceSecurityConfig),
 * never from a client-supplied header. In the demo Keycloak realm, alice has
 * only loan-officer (can submit, gets 403 on approve) and bob has both
 * (can do either).
 */
@RestController
@RequestMapping("/loan")
@RequiredArgsConstructor
public class LoanController {

    static final String IDEMPOTENCY_KEY_HEADER = "Idempotency-Key";
    static final String IDEMPOTENT_REPLAY_HEADER = "Idempotent-Replay";

    private final LoanApplicationService loanApplicationService;

    /**
     * Submitting the same request twice - a client retry after a timeout, say -
     * would otherwise create two separate loan applications. Passing an
     * {@code Idempotency-Key} header makes the retry safe: the original loan is
     * returned and no second LOAN_SUBMITTED event is published. The response
     * carries {@code Idempotent-Replay: true} so the caller can tell the
     * difference. The header is optional, so existing clients are unaffected.
     */
    @PostMapping
    @PreAuthorize("hasRole('loan-officer')")
    ResponseEntity<LoanApplicationResponse> submit(@Valid @RequestBody LoanApplicationRequest request,
                                                     @RequestHeader(value = IDEMPOTENCY_KEY_HEADER, required = false)
                                                     String idempotencyKey,
                                                     @AuthenticationPrincipal Jwt jwt) {
        var result = loanApplicationService.submit(request, jwt, idempotencyKey);
        return ResponseEntity.status(HttpStatus.CREATED)
                .header(IDEMPOTENT_REPLAY_HEADER, Boolean.toString(result.replayed()))
                .body(LoanApplicationResponse.from(result.loan()));
    }

    @PostMapping("/{id}/approve")
    @PreAuthorize("hasRole('loan-admin')")
    ResponseEntity<LoanApplicationResponse> approve(@PathVariable String id, @AuthenticationPrincipal Jwt jwt) {
        var loan = loanApplicationService.approve(id, jwt);
        return ResponseEntity.ok(LoanApplicationResponse.from(loan));
    }

    @GetMapping("/{id}")
    ResponseEntity<LoanApplicationResponse> get(@PathVariable String id, @AuthenticationPrincipal Jwt jwt) {
        return ResponseEntity.ok(LoanApplicationResponse.from(loanApplicationService.get(id, jwt)));
    }
}
