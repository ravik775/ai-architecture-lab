package org.ex.loanservice.service;

import org.ex.loanservice.controller.LoanApplicationRequest;
import org.ex.loanservice.domain.LoanApplication;
import org.ex.loanservice.messaging.LoanEventPublisher;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Collections;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

/**
 * Idempotent submission.
 *
 * A client that times out waiting for POST /loan has no way to know whether the
 * loan was created. Retrying without an Idempotency-Key silently creates a
 * second loan application; retrying with one must return the first.
 */
class LoanApplicationServiceIdempotencyTest {

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

    private LoanApplicationRequest request() {
        return new LoanApplicationRequest("Carol Test", BigDecimal.valueOf(15000));
    }

    @Test
    void sameKeyTwice_returnsTheOriginalLoan_andPublishesOnlyOnce() {
        // Scenario: the client's first POST succeeded server-side but the
        // response was lost, so it retries with the same Idempotency-Key. It
        // must get the SAME loan back - not a second one - and the downstream
        // LOAN_SUBMITTED event must not be published twice, or the notification
        // consumer would act on a loan that does not exist as a separate record.
        Jwt alice = jwtFor("alice-id", "tenant-a");

        SubmitResult first = service.submit(request(), alice, "key-1");
        SubmitResult retry = service.submit(request(), alice, "key-1");

        assertThat(first.replayed()).isFalse();
        assertThat(retry.replayed()).isTrue();
        assertThat(retry.loan().getId()).isEqualTo(first.loan().getId());
        verify(eventPublisher, times(1)).publishSubmitted(any());
    }

    @Test
    void differentKeys_createSeparateLoans() {
        // Scenario: two genuinely different applications from the same officer.
        // Idempotency must not collapse them into one.
        Jwt alice = jwtFor("alice-id", "tenant-a");

        SubmitResult one = service.submit(request(), alice, "key-1");
        SubmitResult two = service.submit(request(), alice, "key-2");

        assertThat(two.loan().getId()).isNotEqualTo(one.loan().getId());
        assertThat(two.replayed()).isFalse();
        verify(eventPublisher, times(2)).publishSubmitted(any());
    }

    @Test
    void noKeySupplied_alwaysCreatesANewLoan() {
        // Scenario: existing clients that do not send the header must be
        // unaffected - the header is optional, and without it there is no basis
        // for deduplication, so each call is a distinct application.
        Jwt alice = jwtFor("alice-id", "tenant-a");

        SubmitResult one = service.submit(request(), alice, null);
        SubmitResult two = service.submit(request(), alice, "");

        assertThat(two.loan().getId()).isNotEqualTo(one.loan().getId());
        assertThat(one.replayed()).isFalse();
        assertThat(two.replayed()).isFalse();
        verify(eventPublisher, times(2)).publishSubmitted(any());
    }

    @Test
    void sameKeyFromDifferentTenants_doesNotLeakAcrossTenants() {
        // Scenario: THE security case. Idempotency keys are client-chosen, so
        // two tenants will inevitably pick the same trivial value ("1",
        // "retry"). If the key were not scoped by tenant, tenant-b's submit
        // would "replay" and hand back tenant-a's loan - a cross-tenant data
        // leak triggered by nothing more than a common string.
        Jwt alice = jwtFor("alice-id", "tenant-a");
        Jwt bob = jwtFor("bob-id", "tenant-b");

        SubmitResult aliceResult = service.submit(request(), alice, "shared-key");
        SubmitResult bobResult = service.submit(request(), bob, "shared-key");

        assertThat(bobResult.replayed()).isFalse();
        assertThat(bobResult.loan().getId()).isNotEqualTo(aliceResult.loan().getId());
        assertThat(aliceResult.loan().getTenant()).isEqualTo("tenant-a");
        assertThat(bobResult.loan().getTenant()).isEqualTo("tenant-b");
    }

    @Test
    void concurrentRetriesWithTheSameKey_createExactlyOneLoan() {
        // Scenario: an impatient client (or a proxy retry) fires the same
        // keyed request several times at once. Naive check-then-insert would
        // let several threads all miss the key and each create a loan. Exactly
        // one loan id must exist across all responses, and exactly one event
        // must be published.
        Jwt alice = jwtFor("alice-id", "tenant-a");
        int attempts = 16;
        ExecutorService pool = Executors.newFixedThreadPool(attempts);
        CountDownLatch ready = new CountDownLatch(attempts);
        CountDownLatch go = new CountDownLatch(1);
        Set<String> loanIds = Collections.newSetFromMap(new ConcurrentHashMap<>());

        try {
            for (int i = 0; i < attempts; i++) {
                pool.submit(() -> {
                    ready.countDown();
                    try {
                        go.await();
                        loanIds.add(service.submit(request(), alice, "concurrent-key").loan().getId());
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            go.countDown();
            pool.shutdown();
            assertThat(pool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new AssertionError(e);
        }

        assertThat(loanIds).hasSize(1);
        verify(eventPublisher, times(1)).publishSubmitted(any());
    }

    @Test
    void replayedLoan_isTheSameStoredRecord() {
        // Scenario: the replayed response must reflect the loan's CURRENT
        // state, not a stale copy captured at creation - otherwise a client
        // retrying after the loan was approved would be told it is still
        // PENDING.
        Jwt alice = jwtFor("alice-id", "tenant-a");
        SubmitResult first = service.submit(request(), alice, "key-1");
        service.approve(first.loan().getId(), jwtFor("bob-id", "tenant-a"));

        LoanApplication replayed = service.submit(request(), alice, "key-1").loan();

        assertThat(replayed.getStatus()).isEqualTo(org.ex.loanservice.domain.LoanStatus.APPROVED);
        assertThat(replayed.getApprovedBy()).isEqualTo("bob-id");
    }
}
