package org.ex.apigateway.service;

import io.github.bucket4j.Bandwidth;
import io.github.bucket4j.BucketConfiguration;
import io.github.bucket4j.ConsumptionProbe;
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
    private final ConcurrentHashMap<String, TenantLease> localLeases = new ConcurrentHashMap<>();

    @Value("${local.ratelimiter.leaseSize}")
    private long leaseSize;

    /**
     * Reactive entry point. Fast path (local tokens available) resolves
     * synchronously but is still wrapped in Mono.just so callers always get
     * a non-blocking pipeline. Slow path (needs a new lease from Redis) uses
     * Bucket4j's async CAS API so it never blocks the WebFlux event loop.
     */
    public Mono<RateLimitResult> consume(String tenantId) {
        TenantPolicy policy = policyService.getPolicy(tenantId);
        TenantLease lease = localLeases.computeIfAbsent(tenantId, id -> new TenantLease());

        log.info("Tenant={} requestsPerMinute={} burstCapacity={}",
                tenantId, policy.getRequestsPerMinute(), policy.getBurstCapacity());

        if (lease.tryConsume()) {
            return Mono.just(RateLimitResult.builder()
                    .allowed(true)
                    .limit(policy.getRequestsPerMinute())
                    .remaining(Math.min(policy.getBurstCapacity(), lease.approximateRemaining()))
                    .approximateRemaining(true)
                    .build());
        }

        return leaseFromGlobalBucket(tenantId, policy, lease);
    }

    private Mono<RateLimitResult> leaseFromGlobalBucket(String tenantId, TenantPolicy policy, TenantLease lease) {
        AsyncBucketProxy globalBucket = getGlobalBucketAsync(tenantId, policy);
        long effectiveLeaseSize = Math.min(leaseSize, policy.getBurstCapacity());

        return Mono.fromFuture(globalBucket.tryConsumeAndReturnRemaining(effectiveLeaseSize))
                .map(leaseProbe -> {
                    if (!leaseProbe.isConsumed()) {
                        long retryAfter = leaseProbe.getNanosToWaitForRefill() / 1_000_000_000;
                        log.info("Tenant={} rate limited retryAfter={}s", tenantId, retryAfter);
                        return RateLimitResult.builder()
                                .allowed(false)
                                .limit(policy.getRequestsPerMinute())
                                .remaining(0)
                                .retryAfterSeconds(retryAfter)
                                .build();
                    }

                    lease.addLease(effectiveLeaseSize, leaseProbe.getRemainingTokens());
                    log.info("Tenant={} leaseGranted globalRemaining={} localRemaining={}",
                            tenantId, leaseProbe.getRemainingTokens(), lease.getLocalRemaining().get());

                    lease.tryConsume();

                    return RateLimitResult.builder()
                            .allowed(true)
                            .limit(policy.getRequestsPerMinute())
                            .remaining(Math.min(policy.getBurstCapacity(), lease.approximateRemaining()))
                            .approximateRemaining(true)
                            .build();
                });
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