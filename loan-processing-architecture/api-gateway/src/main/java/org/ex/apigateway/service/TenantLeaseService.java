package org.ex.apigateway.service;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import io.github.bucket4j.Bandwidth;
import io.github.bucket4j.BucketConfiguration;
import io.github.bucket4j.distributed.AsyncBucketProxy;
import io.github.bucket4j.distributed.proxy.ProxyManager;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.ex.apigateway.config.TenantLease;
import org.ex.apigateway.model.RateLimitResult;
import org.ex.apigateway.model.TenantPolicy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;

@Slf4j
@Service
@RequiredArgsConstructor
public class TenantLeaseService {

    private final TenantPolicyService policyService;
    private final ProxyManager<String> proxyManager;

    /**
     * Bounded and time-limited, unlike a plain ConcurrentHashMap: an entry
     * that sees no traffic for a minute is evicted. This caps memory for a
     * long-running gateway (idle tenants used to accumulate forever) and
     * also stops a tenant's local lease from staying valid indefinitely -
     * without it, an idle tenant could accumulate leased tokens and later
     * burst past the rate the policy's "per minute" window is meant to cap.
     */
    private final Cache<String, TenantLease> localLeases = Caffeine.newBuilder()
            .expireAfterWrite(Duration.ofMinutes(1))
            .maximumSize(100_000)
            .build();

    /**
     * Coalesces concurrent global-bucket lease calls for the same tenant.
     * Without this, N requests that all miss the local lease at once each
     * independently draw a full leaseSize batch from the global bucket - N
     * times the intended budget consumed for what should cost a single
     * lease. Losers instead await the one in-flight lease and then compete
     * locally for the tokens it added, same as if the local bucket had
     * simply been refilled just before they arrived. Entries are removed as
     * soon as the shared lease completes, so this map is always transient.
     */
    private final ConcurrentHashMap<String, Mono<Boolean>> inFlightLeases = new ConcurrentHashMap<>();

    @Value("${local.ratelimiter.leaseSize}")
    private long leaseSize;

    /**
     * Reactive entry point, non-blocking end to end.
     *
     * The policy lookup is now a Mono (it used to be a blocking Redis call made
     * directly on the event loop). Fast path - local tokens already leased -
     * resolves without touching Redis at all; slow path uses Bucket4j's async
     * CAS API.
     */
    public Mono<RateLimitResult> consume(String tenantId) {
        return policyService.getPolicy(tenantId)
                .flatMap(policy -> {
                    TenantLease lease = localLeases.get(tenantId, id -> new TenantLease());

                    log.debug("Tenant={} requestsPerMinute={} burstCapacity={}",
                            tenantId, policy.getRequestsPerMinute(), policy.getBurstCapacity());

                    if (lease.tryConsume()) {
                        return Mono.just(allowedResult(policy, lease));
                    }

                    return acquireLease(tenantId, policy, lease)
                            .map(v -> lease.tryConsume()
                                    ? allowedResult(policy, lease)
                                    : deniedResult(policy, lease));
                });
    }

    private Mono<Boolean> acquireLease(String tenantId, TenantPolicy policy, TenantLease lease) {
        return inFlightLeases.computeIfAbsent(tenantId, id ->
                leaseFromGlobalBucket(tenantId, policy, lease)
                        .doFinally(signal -> inFlightLeases.remove(tenantId))
                        .cache());
    }

    /**
     * Mono<Boolean> rather than Mono<Void> deliberately: Mono<Void> completes
     * via onComplete with no onNext signal, so a downstream .map(v -> ...) on
     * it never runs its function at all - consume() would silently complete
     * empty every time a lease had to be drawn from the global bucket, and
     * TenantRateLimiterGlobalFilter's switchIfEmpty would misreport that as a
     * missing-tenant 403. The returned Boolean itself is unused; only its
     * presence as an onNext value matters.
     */
    private Mono<Boolean> leaseFromGlobalBucket(String tenantId, TenantPolicy policy, TenantLease lease) {
        AsyncBucketProxy globalBucket = getGlobalBucketAsync(tenantId, policy);
        long effectiveLeaseSize = Math.min(leaseSize, policy.getBurstCapacity());

        return Mono.fromFuture(globalBucket.tryConsumeAndReturnRemaining(effectiveLeaseSize))
                .doOnNext(leaseProbe -> {
                    if (!leaseProbe.isConsumed()) {
                        long retryAfter = ceilSecondsAtLeastOne(leaseProbe.getNanosToWaitForRefill());
                        lease.setLastRetryAfterSeconds(retryAfter);
                        log.info("Tenant={} rate limited retryAfter={}s", tenantId, retryAfter);
                        return;
                    }

                    lease.addLease(effectiveLeaseSize, leaseProbe.getRemainingTokens());
                    log.debug("Tenant={} leaseGranted globalRemaining={} localRemaining={}",
                            tenantId, leaseProbe.getRemainingTokens(), lease.getLocalRemaining().get());
                })
                .thenReturn(Boolean.TRUE);
    }

    /**
     * Ceiling division with a floor of 1. Plain integer division
     * (nanos / 1_000_000_000) truncates any wait under one second to 0,
     * which sends Retry-After: 0 - a correctly-behaved client retries
     * immediately, gets rate-limited again, and the throttle becomes a
     * retry storm instead of shedding load.
     */
    static long ceilSecondsAtLeastOne(long nanos) {
        return Math.max(1, (nanos + 999_999_999) / 1_000_000_000);
    }

    private RateLimitResult allowedResult(TenantPolicy policy, TenantLease lease) {
        return RateLimitResult.builder()
                .allowed(true)
                .limit(policy.getRequestsPerMinute())
                .remaining(Math.min(policy.getBurstCapacity(), lease.approximateRemaining()))
                .approximateRemaining(true)
                .build();
    }

    private RateLimitResult deniedResult(TenantPolicy policy, TenantLease lease) {
        return RateLimitResult.builder()
                .allowed(false)
                .limit(policy.getRequestsPerMinute())
                .remaining(0)
                .retryAfterSeconds(lease.getLastRetryAfterSeconds())
                .build();
    }

    private AsyncBucketProxy getGlobalBucketAsync(String tenantId, TenantPolicy policy) {
        Bandwidth bandwidth = Bandwidth.builder()
                .capacity(policy.getBurstCapacity())
                .refillGreedy(policy.getRequestsPerMinute(), Duration.ofMinutes(1))
                .build();

        BucketConfiguration configuration = BucketConfiguration.builder()
                .addLimit(bandwidth)
                .build();

        return proxyManager.asAsync()
                .builder()
                .build("tenant:" + tenantId, () -> CompletableFuture.completedFuture(configuration));
    }
}
