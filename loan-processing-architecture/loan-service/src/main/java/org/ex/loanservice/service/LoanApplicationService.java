package org.ex.loanservice.service;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import lombok.RequiredArgsConstructor;
import org.ex.loanservice.controller.LoanApplicationRequest;
import org.ex.loanservice.domain.LoanApplication;
import org.ex.loanservice.messaging.LoanEventPublisher;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

/**
 * In-memory only, on purpose - JPA/MySQL are deliberately not wired in this
 * codebase (see the commented-out dependencies in loan-service/pom.xml).
 * This is a demo of the OIDC role-authorization + async-eventing concepts,
 * not a persistence layer.
 */
@Service
@RequiredArgsConstructor
public class LoanApplicationService {

    /**
     * Bounded and time-limited, unlike a plain ConcurrentHashMap: a
     * long-running demo process used to accumulate every loan ever created
     * with no eviction, growing until OOM. 24h/50k is generous for a demo
     * workload while giving both maps an actual ceiling.
     */
    private final Cache<String, LoanApplication> store = Caffeine.newBuilder()
            .maximumSize(50_000)
            .expireAfterWrite(Duration.ofHours(24))
            .build();

    /** Maps a tenant-scoped Idempotency-Key to the loan id it originally created. */
    private final Cache<String, String> idempotencyKeys = Caffeine.newBuilder()
            .maximumSize(50_000)
            .expireAfterWrite(Duration.ofHours(24))
            .build();

    private final LoanEventPublisher eventPublisher;

    /**
     * Submits a loan, optionally under an Idempotency-Key.
     *
     * Without a key this creates a new loan every time - so a client that
     * retries after a network timeout, having no way to know whether the first
     * attempt was applied, silently creates a duplicate loan application.
     * Supplying a key makes the retry safe: the original loan is returned
     * instead, and the LOAN_SUBMITTED event is published exactly once.
     *
     * The key is scoped by tenant. A bare key would let one tenant's chosen key
     * collide with another's and hand back a loan belonging to a different
     * tenant - a cross-tenant data leak triggered by nothing more than a common
     * value like "1".
     */
    public SubmitResult submit(LoanApplicationRequest request, Jwt jwt, String idempotencyKey) {
        if (idempotencyKey == null || idempotencyKey.isBlank()) {
            return new SubmitResult(createAndPublish(request, jwt), false);
        }

        String scopedKey = tenantOf(jwt) + "::" + idempotencyKey;

        // computeIfAbsent gives per-key mutual exclusion, so two concurrent
        // retries cannot both create a loan. Only the record is built inside the
        // mapping function - publishing happens after, because doing broker I/O
        // while holding the cache's per-key lock would block unrelated keys.
        boolean[] created = { false };
        String loanId = idempotencyKeys.asMap().computeIfAbsent(scopedKey, key -> {
            LoanApplication loan = build(request, jwt);
            store.put(loan.getId(), loan);
            created[0] = true;
            return loan.getId();
        });

        LoanApplication loan = store.getIfPresent(loanId);
        if (created[0]) {
            eventPublisher.publishSubmitted(loan);
            return new SubmitResult(loan, false);
        }
        return new SubmitResult(loan, true);
    }

    private LoanApplication createAndPublish(LoanApplicationRequest request, Jwt jwt) {
        LoanApplication loan = build(request, jwt);
        store.put(loan.getId(), loan);
        eventPublisher.publishSubmitted(loan);
        return loan;
    }

    private LoanApplication build(LoanApplicationRequest request, Jwt jwt) {
        return LoanApplication.builder()
                .id(UUID.randomUUID().toString())
                .applicantName(request.applicantName())
                .amount(request.amount())
                .tenant(tenantOf(jwt))
                .submittedBy(jwt.getSubject())
                .submittedAt(Instant.now())
                .build();
    }

    /**
     * Never trusts that api-gateway already rejected a tenant-less token
     * (see LoanServiceSecurityConfig's comment on independent re-validation).
     * Without this check a token missing the claim would silently store
     * tenant=null instead of failing closed.
     */
    private static String tenantOf(Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant");
        if (tenant == null || tenant.isBlank()) {
            throw new MissingTenantClaimException(jwt.getSubject());
        }
        return tenant;
    }

    public LoanApplication approve(String id, Jwt jwt) {
        LoanApplication loan = requireOwnedByCaller(id, jwt);

        // tryApprove CASes PENDING -> APPROVED atomically, so two concurrent
        // approve calls for the same loan can't both see PENDING and both "win".
        if (!loan.tryApprove(jwt.getSubject(), Instant.now())) {
            throw new InvalidLoanStateException(id, loan.getStatus());
        }

        eventPublisher.publishApproved(loan);
        return loan;
    }

    public LoanApplication get(String id, Jwt jwt) {
        return requireOwnedByCaller(id, jwt);
    }

    /**
     * Loans are tenant-owned: a valid loan-officer/loan-admin token for
     * tenant A must not be able to view or approve tenant B's loan just by
     * knowing its id (OWASP API1:2023 Broken Object Level Authorization).
     * Both "no such loan" and "exists, but not your tenant's" throw the same
     * LoanNotFoundException - a 403 or any response that tells the two apart
     * would let a caller enumerate which loan ids exist in other tenants.
     */
    private LoanApplication requireOwnedByCaller(String id, Jwt jwt) {
        LoanApplication loan = store.getIfPresent(id);
        if (loan == null || !loan.getTenant().equals(tenantOf(jwt))) {
            throw new LoanNotFoundException(id);
        }
        return loan;
    }
}
