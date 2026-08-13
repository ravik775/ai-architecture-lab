package org.ex.loanservice.config;

import org.springframework.boot.ssl.SslBundles;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;

@Configuration
public class RestTemplateConfig {

    /**
     * Outbound HTTP client for service-to-service calls, built on the SPIFFE
     * SSL bundle.
     *
     * This previously used a bare SimpleClientHttpRequestFactory with no TLS
     * material at all. Nothing about that was visibly wrong - it just meant any
     * internal call made through this bean would present no client certificate
     * and trust the JVM default trust store, silently bypassing the mTLS the
     * rest of the architecture depends on. In a service whose entire premise is
     * that callers must prove workload identity, an un-identified HTTP client
     * sitting in the context is a trap for the next person who injects it.
     *
     * Binding it to the same "spiffe" bundle used by the server connector means
     * it presents this workload's SVID and validates peers against the SPIRE
     * trust bundle - and, because the bundle is declared with
     * reload-on-update: true, it follows SVID rotation as well.
     *
     * Timeouts are retained and matter: without them a hung peer parks the
     * calling thread indefinitely and the bulkhead protecting it is useless,
     * because the permit is never released.
     *
     * @LoadBalanced makes Spring Cloud LoadBalancer rewrite a logical service
     * name (e.g. "payment-service") into an actual instance address from the
     * Eureka registry before this RestTemplate executes the call - callers
     * are not allowed to hardcode a host:port and quietly bypass service
     * discovery.
     */
    @Bean
    @LoadBalanced
    public RestTemplate restTemplate(RestTemplateBuilder builder, SslBundles sslBundles) {
        return builder
                .sslBundle(sslBundles.getBundle("spiffe"))
                .connectTimeout(Duration.ofSeconds(2))
                .readTimeout(Duration.ofSeconds(2))
                .build();
    }
}
