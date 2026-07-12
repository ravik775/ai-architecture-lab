package org.ex.apigateway.config;

import lombok.Data;

import java.util.concurrent.atomic.AtomicLong;

@Data
public class TenantLease {

    private final AtomicLong localRemaining = new AtomicLong(0);
    private volatile long globalSnapshotRemaining;

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