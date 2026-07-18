package org.ex.apigateway.config;

import org.ex.apigateway.filter.TenantRateLimiterGlobalFilter;
import org.ex.apigateway.service.TenantLeaseService;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TenantRateLimiterConfiguration {

    /**
     * Replaces the old MVC-only SimpleFilterSupplier(TenantFilterFunctions.class).
     * A GlobalFilter is the WebFlux-native way to apply a cross-cutting filter
     * to every route without referencing it by name in each route's filter list.
     */
    @Bean
    public GlobalFilter tenantRateLimiterFilter(TenantLeaseService leaseService) {
        return new TenantRateLimiterGlobalFilter(leaseService);
    }
}