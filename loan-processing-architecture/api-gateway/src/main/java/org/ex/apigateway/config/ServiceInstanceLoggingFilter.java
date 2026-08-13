package org.ex.apigateway.config;

import lombok.extern.slf4j.Slf4j;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.net.URI;

/**
 * Logs which concrete service instance a request was load-balanced onto.
 *
 * Implements Ordered explicitly: a GlobalFilter that does not gets whatever
 * position the framework assigns, which for a filter that reads
 * GATEWAY_REQUEST_URL_ATTR is a correctness concern rather than cosmetics - run
 * it before ReactiveLoadBalancerClientFilter (order 10150) has resolved
 * lb://SERVICE and the attribute is still the unresolved URI, so the log line
 * would silently be wrong.
 */
@Component
@Slf4j
public class ServiceInstanceLoggingFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        // Just after ReactiveLoadBalancerClientFilter (10150) and its cookie
        // filter (10151), so the resolved instance URI is available.
        return 10155;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {

        if (log.isDebugEnabled()) {
            URI uri = exchange.getAttribute(
                    ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR);
            log.debug("Gateway target URI = {}", uri);
        }

        return chain.filter(exchange);
    }
}
