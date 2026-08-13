package org.ex.loanservice.service;

import org.ex.loanservice.controller.LoanApplicationRequest;
import org.ex.loanservice.domain.LoanApplication;
import org.ex.loanservice.domain.LoanStatus;
import org.ex.loanservice.messaging.LoanEventPublisher;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

/**
 * Covers the in-memory loan store's business rules directly (no Spring
 * context, no HTTP, no broker) - the publisher is mocked so these tests
 * isolate submit/approve/get from RabbitMQ entirely.
 */
class LoanApplicationServiceTest {

    private LoanEventPublisher eventPublisher;
    private LoanApplicationService service;

    @BeforeEach
    void setUp() {
        eventPublisher = mock(LoanEventPublisher.class);
        service = new LoanApplicationService(eventPublisher);
    }

    private Jwt jwtFor(String subject, String tenant) {
        return Jwt.withTokenValue("token")
                .header("alg", "none")
                .subject(subject)
                .claim("tenant", tenant)
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(300))
                .build();
    }

    private Jwt jwtWithoutTenantClaim(String subject) {
        return Jwt.withTokenValue("token")
                .header("alg", "none")
                .subject(subject)
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(300))
                .build();
    }

    @Test
    void submit_throwsMissingTenantClaimException_whenJwtHasNoTenantClaim() {
        // Scenario: loan-service must not trust that api-gateway already
        // rejected a tenant-less token - it independently re-checks. A JWT
        // missing the "tenant" claim must fail closed (no loan stored with
        // tenant=null), not silently succeed.
        LoanApplicationRequest request = new LoanApplicationRequest("Jack Test", BigDecimal.valueOf(1000));

        assertThatThrownBy(() -> service.submit(request, jwtWithoutTenantClaim("jack-id"), null))
                .isInstanceOf(MissingTenantClaimException.class);

        verify(eventPublisher, never()).publishSubmitted(any());
    }

    @Test
    void submit_throwsMissingTenantClaimException_whenTenantClaimIsBlank() {
        // Scenario: same fail-closed requirement for a tenant claim present
        // but empty/whitespace-only, not just absent.
        LoanApplicationRequest request = new LoanApplicationRequest("Kate Test", BigDecimal.valueOf(1000));

        assertThatThrownBy(() -> service.submit(request, jwtFor("kate-id", "  "), null))
                .isInstanceOf(MissingTenantClaimException.class);

        verify(eventPublisher, never()).publishSubmitted(any());
    }

    @Test
    void submit_createsLoanInPendingStatus_withFieldsTakenFromRequestAndJwt() {
        // Scenario: an authenticated loan-officer (subject "alice-id", tenant
        // "tenant-a") submits a new loan application. The resulting record
        // must carry the request's applicant/amount, the tenant and
        // submitter identity pulled from the verified JWT (never trusted
        // from client input), start life as PENDING, and have no approval
        // fields set yet.
        LoanApplicationRequest request = new LoanApplicationRequest("Carol Test", BigDecimal.valueOf(15000));
        Jwt aliceJwt = jwtFor("alice-id", "tenant-a");

        LoanApplication loan = service.submit(request, aliceJwt, null).loan();

        assertThat(loan.getId()).isNotBlank();
        assertThat(loan.getApplicantName()).isEqualTo("Carol Test");
        assertThat(loan.getAmount()).isEqualByComparingTo("15000");
        assertThat(loan.getTenant()).isEqualTo("tenant-a");
        assertThat(loan.getSubmittedBy()).isEqualTo("alice-id");
        assertThat(loan.getStatus()).isEqualTo(LoanStatus.PENDING);
        assertThat(loan.getApprovedBy()).isNull();
        assertThat(loan.getApprovedAt()).isNull();
        assertThat(loan.getSubmittedAt()).isNotNull();
    }

    @Test
    void submit_publishesLoanSubmittedEvent() {
        // Scenario: every successful submission must publish a
        // LOAN_SUBMITTED event so LoanNotificationListener (and any future
        // subscriber) can react asynchronously - this is the producer half
        // of the RabbitMQ roundtrip the demo exists to show.
        LoanApplicationRequest request = new LoanApplicationRequest("Dave Test", BigDecimal.valueOf(5000));

        LoanApplication loan = service.submit(request, jwtFor("dave-id", "tenant-a"), null).loan();

        verify(eventPublisher, times(1)).publishSubmitted(loan);
        verify(eventPublisher, never()).publishApproved(any());
    }

    @Test
    void approve_transitionsPendingLoanToApproved_andRecordsApprover() {
        // Scenario: a loan-admin (e.g. "bob") approves a loan that is
        // currently PENDING. Status must flip to APPROVED and the approver's
        // JWT subject/timestamp must be recorded - this is the state change
        // the whole authorization demo is built to protect.
        LoanApplication submitted = service.submit(
                new LoanApplicationRequest("Erin Test", BigDecimal.valueOf(2000)),
                jwtFor("alice-id", "tenant-a"), null).loan();

        LoanApplication approved = service.approve(submitted.getId(), jwtFor("bob-id", "tenant-a"));

        assertThat(approved.getStatus()).isEqualTo(LoanStatus.APPROVED);
        assertThat(approved.getApprovedBy()).isEqualTo("bob-id");
        assertThat(approved.getApprovedAt()).isNotNull();
    }

    @Test
    void approve_publishesLoanApprovedEvent() {
        // Scenario: approval must publish a LOAN_APPROVED event, the
        // consumer half of which is verified separately in
        // LoanNotificationListenerTest.
        LoanApplication submitted = service.submit(
                new LoanApplicationRequest("Frank Test", BigDecimal.valueOf(3000)),
                jwtFor("alice-id", "tenant-a"), null).loan();

        LoanApplication approved = service.approve(submitted.getId(), jwtFor("bob-id", "tenant-a"));

        verify(eventPublisher).publishApproved(approved);
    }

    @Test
    void approve_throwsLoanNotFoundException_whenLoanIdDoesNotExist() {
        // Scenario: approving an id that was never submitted (typo, wrong
        // tenant, forged id) must fail with a 404-mapped exception, not
        // silently succeed or NPE.
        assertThatThrownBy(() -> service.approve("does-not-exist", jwtFor("bob-id", "tenant-b")))
                .isInstanceOf(LoanNotFoundException.class);

        verify(eventPublisher, never()).publishApproved(any());
    }

    @Test
    void approve_throwsInvalidLoanStateException_whenLoanAlreadyApproved() {
        // Scenario: a second approval attempt on an already-APPROVED loan
        // (e.g. bob double-clicks, or a retried request) must be rejected
        // with a 409-mapped conflict rather than silently re-approving or
        // overwriting the original approver/timestamp. Both approval
        // attempts come from tenant-a admins - this test is about the
        // already-approved conflict, not tenant isolation (see the dedicated
        // cross-tenant tests below for that).
        LoanApplication submitted = service.submit(
                new LoanApplicationRequest("Grace Test", BigDecimal.valueOf(1000)),
                jwtFor("alice-id", "tenant-a"), null).loan();
        LoanApplication firstApproval = service.approve(submitted.getId(), jwtFor("bob-id", "tenant-a"));

        assertThatThrownBy(() -> service.approve(submitted.getId(), jwtFor("carol-id", "tenant-a")))
                .isInstanceOf(InvalidLoanStateException.class);

        // approver/timestamp from the first approval must be untouched
        LoanApplication stillApproved = service.get(submitted.getId(), jwtFor("bob-id", "tenant-a"));
        assertThat(stillApproved.getApprovedBy()).isEqualTo(firstApproval.getApprovedBy());
        assertThat(stillApproved.getApprovedAt()).isEqualTo(firstApproval.getApprovedAt());
        // only the first, successful approval publishes an event
        verify(eventPublisher, times(1)).publishApproved(any());
    }

    @Test
    void approve_isAtomicUnderConcurrentApprovalAttempts() throws InterruptedException {
        // Scenario: two threads race to approve the same PENDING loan at
        // the same time (e.g. two admin tabs open). The store uses
        // ConcurrentHashMap#computeIfPresent specifically so this can't
        // double-approve - exactly one caller must see PENDING and win;
        // the other must see the already-approved conflict.
        LoanApplication submitted = service.submit(
                new LoanApplicationRequest("Henry Test", BigDecimal.valueOf(4000)),
                jwtFor("alice-id", "tenant-a"), null).loan();

        int attempts = 20;
        ExecutorService pool = Executors.newFixedThreadPool(attempts);
        CountDownLatch ready = new CountDownLatch(attempts);
        CountDownLatch go = new CountDownLatch(1);
        AtomicInteger successCount = new AtomicInteger();
        AtomicInteger conflictCount = new AtomicInteger();

        for (int i = 0; i < attempts; i++) {
            final int idx = i;
            pool.submit(() -> {
                ready.countDown();
                try {
                    go.await();
                    service.approve(submitted.getId(), jwtFor("approver-" + idx, "tenant-a"));
                    successCount.incrementAndGet();
                } catch (InvalidLoanStateException e) {
                    conflictCount.incrementAndGet();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
        }

        ready.await(5, TimeUnit.SECONDS);
        go.countDown();
        pool.shutdown();
        assertThat(pool.awaitTermination(5, TimeUnit.SECONDS)).isTrue();

        assertThat(successCount.get()).isEqualTo(1);
        assertThat(conflictCount.get()).isEqualTo(attempts - 1);
        verify(eventPublisher, times(1)).publishApproved(any());
    }

    @Test
    void get_returnsStoredLoan_whenPresent() {
        // Scenario: basic read-back used by callers (and by the demo/Postman
        // flow) to verify state after submit/approve.
        LoanApplication submitted = service.submit(
                new LoanApplicationRequest("Iris Test", BigDecimal.valueOf(500)),
                jwtFor("alice-id", "tenant-a"), null).loan();

        LoanApplication fetched = service.get(submitted.getId(), jwtFor("alice-id", "tenant-a"));

        assertThat(fetched).isSameAs(submitted);
    }

    @Test
    void get_throwsLoanNotFoundException_whenLoanIdUnknown() {
        // Scenario: GET /loan/{id} for a non-existent id must map to 404,
        // not return null or throw an unchecked NPE further up the stack.
        assertThatThrownBy(() -> service.get("unknown-id", jwtFor("alice-id", "tenant-a")))
                .isInstanceOf(LoanNotFoundException.class)
                .hasMessageContaining("unknown-id");
    }

    @Test
    void get_throwsLoanNotFoundException_whenCallerIsADifferentTenant() {
        // Scenario: THE fix this test exists for. bob (tenant-b) must not be
        // able to view alice's (tenant-a) loan just by knowing its id - a 404
        // is returned, identical to a truly unknown id, so a caller can't
        // even confirm the loan exists in another tenant.
        LoanApplication submitted = service.submit(
                new LoanApplicationRequest("Jules Test", BigDecimal.valueOf(2500)),
                jwtFor("alice-id", "tenant-a"), null).loan();

        assertThatThrownBy(() -> service.get(submitted.getId(), jwtFor("bob-id", "tenant-b")))
                .isInstanceOf(LoanNotFoundException.class)
                .hasMessageContaining(submitted.getId());
    }

    @Test
    void approve_throwsLoanNotFoundException_whenCallerIsADifferentTenant() {
        // Scenario: same cross-tenant protection on the approve path - a
        // loan-admin for tenant-b must not be able to approve tenant-a's
        // loan, and the loan's status must remain PENDING afterward.
        LoanApplication submitted = service.submit(
                new LoanApplicationRequest("Kara Test", BigDecimal.valueOf(2500)),
                jwtFor("alice-id", "tenant-a"), null).loan();

        assertThatThrownBy(() -> service.approve(submitted.getId(), jwtFor("bob-id", "tenant-b")))
                .isInstanceOf(LoanNotFoundException.class);

        assertThat(service.get(submitted.getId(), jwtFor("alice-id", "tenant-a")).getStatus())
                .isEqualTo(LoanStatus.PENDING);
        verify(eventPublisher, never()).publishApproved(any());
    }
}
