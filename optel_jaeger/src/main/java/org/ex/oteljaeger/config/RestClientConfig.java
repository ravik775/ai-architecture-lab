package org.ex.oteljaeger.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class RestClientConfig {

    /**
     * Spring Boot auto-configures this builder with an ObservationRestClientCustomizer,
     * so every call made through the resulting RestClient produces a CLIENT span and
     * injects the W3C traceparent header — the mechanism that stitches the "order-service"
     * call into the "inventory-service" call as one trace.
     */
    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder.baseUrl("http://localhost:8091").build();
    }
}
