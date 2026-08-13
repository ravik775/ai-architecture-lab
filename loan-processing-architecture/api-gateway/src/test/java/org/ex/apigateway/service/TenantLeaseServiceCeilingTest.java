package org.ex.apigateway.service;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Direct coverage for the H3 fix: plain integer division
 * (nanos / 1_000_000_000) truncated any sub-second wait to 0, sending
 * Retry-After: 0 and turning the throttle into a client retry storm.
 * ceilSecondsAtLeastOne must round up and never return less than 1.
 */
class TenantLeaseServiceCeilingTest {

    @Test
    void roundsSubSecondWaitUpToOne_notZero() {
        // The exact H3 scenario: refill 400ms away must not truncate to 0.
        assertThat(TenantLeaseService.ceilSecondsAtLeastOne(400_000_000L)).isEqualTo(1);
    }

    @Test
    void zeroNanos_stillFloorsToOne() {
        assertThat(TenantLeaseService.ceilSecondsAtLeastOne(0L)).isEqualTo(1);
    }

    @Test
    void exactlyOneSecond_doesNotRoundUpToTwo() {
        assertThat(TenantLeaseService.ceilSecondsAtLeastOne(1_000_000_000L)).isEqualTo(1);
    }

    @Test
    void oneAndAHalfSeconds_roundsUpToTwo() {
        assertThat(TenantLeaseService.ceilSecondsAtLeastOne(1_500_000_000L)).isEqualTo(2);
    }

    @Test
    void tenSeconds_returnsTenExactly() {
        assertThat(TenantLeaseService.ceilSecondsAtLeastOne(10_000_000_000L)).isEqualTo(10);
    }
}
