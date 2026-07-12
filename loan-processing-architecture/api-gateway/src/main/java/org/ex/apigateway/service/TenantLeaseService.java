package org.ex.apigateway.service;

import io.github.bucket4j.Bandwidth;
import io.github.bucket4j.Bucket;
import io.github.bucket4j.BucketConfiguration;
import io.github.bucket4j.ConsumptionProbe;
import io.github.bucket4j.distributed.proxy.ProxyManager;
import lombok.extern.slf4j.Slf4j;
import org.ex.apigateway.config.TenantLease;
import org.ex.apigateway.model.RateLimitResult;
import org.ex.apigateway.model.TenantPolicy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;

@Service
@Slf4j
public class TenantLeaseService {

    private final int leaseSize;

    private final ProxyManager<String> proxyManager;
    private final TenantPolicyService policyService;

    private final ConcurrentHashMap<String, TenantLease> localLeases =
            new ConcurrentHashMap<>();

    public TenantLeaseService(
            ProxyManager<String> proxyManager,
            TenantPolicyService policyService,
            @Value("${local.ratelimiter.leaseSize:1}") int leaseSize) {

        this.proxyManager = proxyManager;
        this.policyService = policyService;
        this.leaseSize = leaseSize;
    }

    public RateLimitResult consume(String tenantId) {

        TenantPolicy policy =
                policyService.getPolicy(tenantId);

        TenantLease lease =
                localLeases.computeIfAbsent(
                        tenantId,
                        id -> new TenantLease());

        log.info(
                "Tenant={} configuredLeaseSize={} rpm={} burst={}",
                tenantId,
                leaseSize,
                policy.getRequestsPerMinute(),
                policy.getBurstCapacity()
        );

        // Fast path - no Redis roundtrip
        if (lease.tryConsume()) {

            return RateLimitResult.builder()
                    .allowed(true)
                    .limit(policy.getRequestsPerMinute())
                    .remaining(
                            Math.min(
                                    policy.getRequestsPerMinute(),
                                    lease.approximateRemaining()
                            )
                    )
                    .approximateRemaining(true)
                    .build();
        }

        // Local lease exhausted, acquire a new lease from Redis
        Bucket globalBucket = getGlobalBucket(tenantId, policy);

        long effectiveLeaseSize = Math.min( leaseSize,  policy.getBurstCapacity() );

        ConsumptionProbe leaseProbe = globalBucket.tryConsumeAndReturnRemaining( effectiveLeaseSize);

        if (!leaseProbe.isConsumed()) {
            long retryAfter = leaseProbe.getNanosToWaitForRefill() / 1_000_000_000;
            log.info( "Tenant={} rate limited retryAfter={}s", tenantId, retryAfter);
            return RateLimitResult.builder()
                    .allowed(false)
                    .limit(policy.getRequestsPerMinute())
                    .remaining(0)
                    .retryAfterSeconds(retryAfter)
                    .approximateRemaining(true)
                    .build();
        }

        lease.addLease( effectiveLeaseSize, leaseProbe.getRemainingTokens());

        log.info(
                "Tenant={} leased={} globalRemaining={} localRemaining={}",
                tenantId,
                effectiveLeaseSize,
                leaseProbe.getRemainingTokens(),
                lease.getLocalRemaining().get()
        );

        // Consume one token for the current request
        lease.tryConsume();

        return RateLimitResult.builder()
                .allowed(true)
                .limit(policy.getRequestsPerMinute())
                .remaining(
                        Math.min(
                                policy.getRequestsPerMinute(),
                                lease.approximateRemaining()
                        )
                )
                .approximateRemaining(true)
                .build();
    }

    private Bucket getGlobalBucket(
            String tenantId,
            TenantPolicy policy) {

        Bandwidth bandwidth =
                Bandwidth.builder()
                        .capacity(policy.getBurstCapacity())
                        .refillGreedy(
                                policy.getRequestsPerMinute(),
                                Duration.ofMinutes(1)
                        )
                        .build();

        BucketConfiguration configuration =
                BucketConfiguration.builder()
                        .addLimit(bandwidth)
                        .build();

        return proxyManager.builder()
                .build(
                        "tenant-rate-limit:" + tenantId,
                        () -> configuration
                );
    }
}