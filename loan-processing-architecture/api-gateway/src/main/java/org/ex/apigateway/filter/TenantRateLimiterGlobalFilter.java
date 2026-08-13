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
 *
 * Tenant is now derived from the verified JWT "tenant" claim
 * (see TenantFilterFunctions), not from the client-supplied X-Tenant-Id
 * header. By the time this filter runs, Spring Security's resource-server
 * WebFilter has already authenticated the request (SecurityConfig requires
 * .anyExchange().authenticated()), so a missing tenant claim here means the
 * token itself is missing tenant scoping - not that the caller is anonymous.
 * That case now fails closed (403) instead of silently skipping rate
 * limiting, since silently skipping would let an under-scoped token bypass
 * tenant enforcement entirely rather than surfacing the misconfiguration.
 */
@Slf4j
@RequiredArgsConstructor
public class TenantRateLimiterGlobalFilter implements GlobalFilter, Ordered {

    private final TenantLeaseService leaseService;

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        return TenantFilterFunctions.resolveTenant(exchange)
                .flatMap(tenantId -> {
                    exchange.getAttributes().put(TenantFilterFunctions.RESOLVED_TENANT_ATTR, tenantId);
                    return leaseService.consume(tenantId)
                            .flatMap(result -> {
                                // DEBUG: this fires on every request. The rejection
                                // path below stays at INFO because it is the
                                // exceptional, actionable case.
                                log.debug("Tenant={} allowed={} remaining={} retryAfter={}",
                                        tenantId, result.allowed(), result.remaining(), result.retryAfterSeconds());

                                if (!result.allowed()) {
                                    return rejectWithTooManyRequests(exchange, tenantId, result);
                                }
                                return chain.filter(exchange);
                            });
                })
                .switchIfEmpty(Mono.defer(() -> rejectWithMissingTenant(exchange)));
    }

    private Mono<Void> rejectWithMissingTenant(ServerWebExchange exchange) {
        log.warn("Authenticated request had no resolvable tenant claim; rejecting. path={}",
                exchange.getRequest().getPath());
        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(HttpStatus.FORBIDDEN);
        byte[] body = "Request token is missing required tenant scoping".getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(response.bufferFactory().wrap(body)));
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