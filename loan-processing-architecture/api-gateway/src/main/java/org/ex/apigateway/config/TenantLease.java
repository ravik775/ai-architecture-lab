package org.ex.apigateway.config;

import lombok.Data;

import java.util.concurrent.atomic.AtomicLong;

@Data
public class TenantLease {

    private final AtomicLong localRemaining = new AtomicLong(0);
    private volatile long globalSnapshotRemaining;
    /**
     * Retry-After for the most recent global-bucket rejection. Read by
     * requests that lose the local race after a *shared* lease (see
     * TenantLeaseService's single-flight coalescing) - they never called the
     * global bucket themselves, so this is the closest available estimate.
     * Floor of 1 matches the H3 fix: 0 would tell a well-behaved client to
     * retry immediately, turning the throttle into a retry storm.
     */
    private volatile long lastRetryAfterSeconds = 1;

    public boolean tryConsume() {
        while (true) {
            long current = localRemaining.get();
            if (current <= 0) return false;
            if (localRemaining.compareAndSet(current,current - 1))
                return true;
        }
    }

    public void addLease(long leasedTokens, long globalSnapshotRemaining) {
        this.globalSnapshotRemaining = globalSnapshotRemaining;
        localRemaining.addAndGet(leasedTokens);
    }

    public long approximateRemaining() {
        return globalSnapshotRemaining + localRemaining.get();
    }
}