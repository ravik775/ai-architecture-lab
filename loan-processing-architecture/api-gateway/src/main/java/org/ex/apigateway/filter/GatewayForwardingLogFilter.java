package org.ex.apigateway.filter;

import lombok.extern.slf4j.Slf4j;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.net.URI;
import java.util.Set;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils.GATEWAY_ORIGINAL_REQUEST_URL_ATTR;
import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR;
import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR;

@Slf4j
@Component
public class GatewayForwardingLogFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        // Must run after ReactiveLoadBalancerClientFilter, which resolves lb://SERVICE to http://host:port
        return 10160;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
        URI targetUri = exchange.getAttribute(GATEWAY_REQUEST_URL_ATTR);
        Set<URI> originalUris = exchange.getAttribute(GATEWAY_ORIGINAL_REQUEST_URL_ATTR);

        log.info(
                "Gateway forwarding request: method={}, incomingUri={}, routeId={}, routeUri={}, resolvedTargetUri={}, originalUris={}",
                exchange.getRequest().getMethod(),
                exchange.getRequest().getURI(),
                route != null ? route.getId() : null,
                route != null ? route.getUri() : null,
                targetUri,
                originalUris
        );

        return chain.filter(exchange)
                .doOnSuccess(unused -> log.info(
                        "Gateway response: targetUri={}, status={}",
                        targetUri,
                        exchange.getResponse().getStatusCode()
                ))
                .doOnError(error -> log.error(
                        "Gateway forwarding failed: targetUri={}, error={}",
                        targetUri,
                        error.getMessage()
                ));
    }
}