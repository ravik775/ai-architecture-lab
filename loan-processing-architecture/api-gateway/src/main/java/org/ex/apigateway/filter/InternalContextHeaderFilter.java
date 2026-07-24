package org.ex.apigateway.filter;

import lombok.extern.slf4j.Slf4j;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Slf4j
@Component
public class InternalContextHeaderFilter implements GlobalFilter, Ordered {

    private static final String INTERNAL_TENANT_HEADER = "X-Internal-Tenant-Id";
    private static final String INTERNAL_CALLER_HEADER = "X-Internal-Caller-Spiffe-Id";
    private static final String INTERNAL_SOURCE_HEADER = "X-Internal-Source";
    private static final String GATEWAY_SPIFFE_ID = "spiffe://example.org/ns/loan/sa/api-gateway";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        // Read the value TenantRateLimiterGlobalFilter already resolved from
        // the verified JWT and cached - do not re-derive it from any header.
        String tenantId = TenantFilterFunctions.getCachedTenant(exchange)
                .orElseThrow(() -> new IllegalStateException(
                        "InternalContextHeaderFilter ran without a resolved tenant - "
                                + "check filter ordering against TenantRateLimiterGlobalFilter"));

        ServerHttpRequest mutatedRequest = exchange.getRequest()
                .mutate()
                .headers(headers -> {
                    headers.remove("X-Tenant-Id");
                    headers.remove(INTERNAL_TENANT_HEADER);
                    headers.remove(INTERNAL_CALLER_HEADER);
                    headers.remove(INTERNAL_SOURCE_HEADER);
                    headers.set(INTERNAL_TENANT_HEADER, tenantId);
                    headers.set(INTERNAL_CALLER_HEADER, GATEWAY_SPIFFE_ID);
                    headers.set(INTERNAL_SOURCE_HEADER, "api-gateway");
                })
                .build();

        log.debug("Internal context headers prepared for tenant={}", tenantId);
        return chain.filter(exchange.mutate().request(mutatedRequest).build());
    }

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE + 20;
    }
}