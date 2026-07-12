package org.ex.apigateway.config;

import org.springframework.cloud.gateway.server.mvc.filter.SimpleFilterSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TenantRateLimiterConfiguration {

    @Bean
    SimpleFilterSupplier tenantFilterSupplier() {
        return new SimpleFilterSupplier( TenantFilterFunctions.class);
    }
}