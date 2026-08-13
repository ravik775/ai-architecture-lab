package org.ex.apigateway.config;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Plain unit coverage for the local-token bookkeeping TenantLeaseService
 * builds on. No Spring context, no mocks - this is a POJO with atomics.
 */
class TenantLeaseTest {

    @Test
    void tryConsume_fails_whenNoLocalTokensLeased() {
        TenantLease lease = new TenantLease();

        assertThat(lease.tryConsume()).isFalse();
    }

    @Test
    void tryConsume_succeeds_untilLeasedTokensExhausted() {
        TenantLease lease = new TenantLease();
        lease.addLease(2, 10);

        assertThat(lease.tryConsume()).isTrue();
        assertThat(lease.tryConsume()).isTrue();
        assertThat(lease.tryConsume()).isFalse();
    }

    @Test
    void lastRetryAfterSeconds_defaultsToOne_neverZero() {
        // A waiter that loses the local race right after a *shared* lease
        // (single-flight coalescing in TenantLeaseService) and was never
        // itself rejected by the global bucket still needs a safe,
        // non-zero Retry-After - 0 would tell a client to retry immediately.
        TenantLease lease = new TenantLease();

        assertThat(lease.getLastRetryAfterSeconds()).isEqualTo(1);
    }

    @Test
    void approximateRemaining_combinesGlobalSnapshotAndLocalRemaining() {
        TenantLease lease = new TenantLease();
        lease.addLease(3, 7);

        assertThat(lease.approximateRemaining()).isEqualTo(10);
    }
}
