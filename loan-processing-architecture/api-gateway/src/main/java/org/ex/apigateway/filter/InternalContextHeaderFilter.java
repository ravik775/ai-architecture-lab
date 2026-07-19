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

    private static final String EXTERNAL_TENANT_HEADER = "X-Tenant-Id";

    private static final String INTERNAL_TENANT_HEADER = "X-Internal-Tenant-Id";
    private static final String INTERNAL_CALLER_HEADER = "X-Internal-Caller-Spiffe-Id";
    private static final String INTERNAL_SOURCE_HEADER = "X-Internal-Source";

    private static final String GATEWAY_SPIFFE_ID =
            "spiffe://example.org/ns/loan/sa/api-gateway";

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String tenantId = exchange.getRequest()
                .getHeaders()
                .getFirst(EXTERNAL_TENANT_HEADER);

        ServerHttpRequest mutatedRequest = exchange.getRequest()
                .mutate()
                .headers(headers -> {
                    // Remove spoofable client-supplied internal headers.
                    headers.remove(INTERNAL_TENANT_HEADER);
                    headers.remove(INTERNAL_CALLER_HEADER);
                    headers.remove(INTERNAL_SOURCE_HEADER);

                    if (tenantId != null && !tenantId.isBlank()) {
                        headers.set(INTERNAL_TENANT_HEADER, tenantId);
                    }

                    headers.set(INTERNAL_CALLER_HEADER, GATEWAY_SPIFFE_ID);
                    headers.set(INTERNAL_SOURCE_HEADER, "api-gateway");
                })
                .build();

        log.debug("Internal context headers prepared for tenant={}", tenantId);

        return chain.filter(exchange.mutate().request(mutatedRequest).build());
    }

    @Override
    public int getOrder() {
        // Runs after TenantRateLimiterGlobalFilter and before routing.
        return Ordered.HIGHEST_PRECEDENCE + 20;
    }
}