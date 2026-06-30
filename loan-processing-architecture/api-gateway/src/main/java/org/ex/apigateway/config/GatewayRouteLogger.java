package org.ex.apigateway.config;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.gateway.server.mvc.config.GatewayMvcProperties;

@Configuration
public class GatewayRouteLogger {

    @Bean
    CommandLineRunner printRoutes(GatewayMvcProperties properties) {
        return args -> {
            properties.getRoutes().forEach(route -> {
                System.out.println("================================");
                System.out.println("Route ID   : " + route.getId());
                System.out.println("URI        : " + route.getUri());
                System.out.println("Predicates : " + route.getPredicates());
                System.out.println("Filters    : " + route.getFilters());
            });
        };
    }
}