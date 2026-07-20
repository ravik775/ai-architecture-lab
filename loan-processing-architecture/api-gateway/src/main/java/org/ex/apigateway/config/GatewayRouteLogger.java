package org.ex.apigateway.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@Slf4j
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
                    log.info("================================");
                    log.info("Route ID   : " + route.getId());
                    log.info("URI        : " + route.getUri());
                    log.info("Predicate  : " + route.getPredicate());
                    log.info("Filters    : " + route.getFilters());
                })
                .subscribe();
    }
}