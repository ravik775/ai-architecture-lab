package org.ex.apigateway.filter;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.ex.apigateway.model.RateLimitResult;
import org.ex.apigateway.service.TenantLeaseService;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.nio.charset.StandardCharsets;

/**
 * Reactive replacement for the old {@code TenantFilterFunctions} MVC HandlerFilterFunction.
 * Runs as a GlobalFilter so it applies to every route without needing to be
 * wired in per-route via a named filter factory. Bean is declared in
 * {@code TenantRateLimiterConfiguration}.
 */
@Slf4j
@RequiredArgsConstructor
public class TenantRateLimiterGlobalFilter implements GlobalFilter, Ordered {

    private static final String TENANT_HEADER = "X-Tenant-Id";

    private final TenantLeaseService leaseService;

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String tenantId = exchange.getRequest().getHeaders().getFirst(TENANT_HEADER);

        if (tenantId == null || tenantId.isBlank()) {
            return chain.filter(exchange);
        }

        return leaseService.consume(tenantId)
                .flatMap(result -> {
                    log.info("Tenant={} allowed={} remaining={} retryAfter={}",
                            tenantId, result.allowed(), result.remaining(), result.retryAfterSeconds());

                    if (!result.allowed()) {
                        return rejectWithTooManyRequests(exchange, tenantId, result);
                    }
                    return chain.filter(exchange);
                });
    }

    private Mono<Void> rejectWithTooManyRequests(ServerWebExchange exchange, String tenantId, RateLimitResult result) {
        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
        response.getHeaders().add("X-RateLimit-Limit", String.valueOf(result.limit()));
        response.getHeaders().add("X-RateLimit-Remaining", "0");
        response.getHeaders().add("X-RateLimit-Remaining-Approximate", "true");
        response.getHeaders().add("X-RateLimit-Reset", String.valueOf(result.retryAfterSeconds()));
        response.getHeaders().add("Retry-After", String.valueOf(result.retryAfterSeconds()));

        byte[] body = ("Rate limit exceeded for tenant: " + tenantId).getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(response.bufferFactory().wrap(body)));
    }

    @Override
    public int getOrder() {
        // Run early, before the request is proxied to the downstream route
        return Ordered.HIGHEST_PRECEDENCE + 10;
    }
}