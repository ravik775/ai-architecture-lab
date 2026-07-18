package org.ex.apigateway.config;

import io.github.bucket4j.distributed.proxy.ProxyManager;
import io.github.bucket4j.redis.lettuce.Bucket4jLettuce;
import io.lettuce.core.api.StatefulRedisConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class Bucket4jRedisConfiguration {

    /**
     * This proxy manager is CAS-based over a Lettuce connection, which is
     * async-native under the hood — TenantLeaseService calls
     * proxyManager.asAsync() to get a genuinely non-blocking AsyncProxyManager
     * (CompletableFuture-backed) rather than a thread-pool-wrapped shim.
     * No structural change needed here for Phase 0; kept as-is.
     */
    @Bean
    public ProxyManager<String> proxyManager(StatefulRedisConnection<String, byte[]> connection) {
        return Bucket4jLettuce.casBasedBuilder(connection).build();
    }
}