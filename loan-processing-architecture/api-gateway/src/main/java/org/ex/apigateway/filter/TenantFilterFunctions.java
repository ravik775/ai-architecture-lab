package org.ex.apigateway.filter;

import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.util.Optional;

/**
 * Derives the tenant identifier for a request from the verified JWT's
 * "tenant" claim - never from a client-supplied header. By the time this
 * runs, SecurityConfig has already authenticated the request, so the Jwt
 * behind exchange.getPrincipal() has a verified signature/issuer/expiry.
 * A caller cannot forge this the way they could a raw X-Tenant-Id header.
 */
public final class TenantFilterFunctions {

    /**
     * Exchange attribute key used to cache the resolved tenant for the
     * current request, so downstream filters (e.g. InternalContextHeaderFilter)
     * reuse the value already verified earlier in the chain instead of
     * re-parsing the JWT a second time.
     */
    public static final String RESOLVED_TENANT_ATTR = "resolvedTenantId";

    private TenantFilterFunctions() {
    }

    public static Mono<String> resolveTenant(ServerWebExchange exchange) {
        return exchange.getPrincipal()
                .filter(JwtAuthenticationToken.class::isInstance)
                .cast(JwtAuthenticationToken.class)
                .map(JwtAuthenticationToken::getToken)
                .flatMap(TenantFilterFunctions::extractTenantClaim);
    }

    /**
     * Reads the tenant previously resolved and cached by an earlier filter
     * in this same request's chain (see TenantRateLimiterGlobalFilter).
     * Empty means nothing resolved it yet - callers must treat that as
     * "reject", never as "skip tenant enforcement".
     */
    public static Optional<String> getCachedTenant(ServerWebExchange exchange) {
        return Optional.ofNullable(exchange.getAttribute(RESOLVED_TENANT_ATTR));
    }

    private static Mono<String> extractTenantClaim(Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant");
        if (tenant == null || tenant.isBlank()) {
            return Mono.empty();
        }
        return Mono.just(tenant);
    }
}