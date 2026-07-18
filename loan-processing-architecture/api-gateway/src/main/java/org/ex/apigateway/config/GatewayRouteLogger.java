package org.ex.apigateway.config;

import org.springframework.boot.CommandLineRunner;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GatewayRouteLogger {

    /**
     * Reactive route introspection. GatewayMvcProperties (servlet-stack only)
     * is gone on the webflux starter; RouteLocator is the reactive equivalent
     * and exposes routes as a Flux<Route>.
     */
    @Bean
    public CommandLineRunner printRoutes(RouteLocator routeLocator) {
        return args -> routeLocator.getRoutes()
                .doOnNext(route -> {
                    System.out.println("================================");
                    System.out.println("Route ID   : " + route.getId());
                    System.out.println("URI        : " + route.getUri());
                    System.out.println("Predicate  : " + route.getPredicate());
                    System.out.println("Filters    : " + route.getFilters());
                })
                .subscribe();
    }
}