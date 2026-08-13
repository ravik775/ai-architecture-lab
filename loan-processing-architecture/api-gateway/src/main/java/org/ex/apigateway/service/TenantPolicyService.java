package org.ex.apigateway.service;

import lombok.extern.slf4j.Slf4j;
import org.ex.apigateway.model.TenantPolicy;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

/**
 * Looks up per-tenant rate-limit policy.
 *
 * This sits on the request hot path, so the lookup is fully reactive: it
 * previously used the blocking RedisTemplate, which parked a Netty event-loop
 * thread on every single request.
 */
@Slf4j
@Service
public class TenantPolicyService {

    private static final String KEY_PREFIX = "tenant:policy:";

    private final ReactiveRedisTemplate<String, TenantPolicy> template;

    public TenantPolicyService(ReactiveRedisTemplate<String, TenantPolicy> template) {
        this.template = template;
    }

    protected TenantPolicy getDefault(String tenant) {
        TenantPolicy policy = new TenantPolicy();
        policy.setTenantId(tenant);
        policy.setRequestsPerMinute(10);
        policy.setBurstCapacity(8);
        return policy;
    }

    /**
     * Falls back to the default policy both when no policy is stored and when
     * Redis errors. Failing open on the *policy lookup* is deliberate: the
     * default is the most restrictive policy in use, so a Redis outage degrades
     * to standard limits rather than taking the gateway down. The rate limit
     * itself still applies - only the per-tenant override is lost.
     */
    public Mono<TenantPolicy> getPolicy(String tenant) {
        return template.opsForValue()
                .get(KEY_PREFIX + tenant)
                .switchIfEmpty(Mono.fromSupplier(() -> getDefault(tenant)))
                .onErrorResume(ex -> {
                    log.warn("Tenant policy lookup failed for tenant={}, falling back to default policy: {}",
                            tenant, ex.toString());
                    return Mono.fromSupplier(() -> getDefault(tenant));
                });
    }
}
