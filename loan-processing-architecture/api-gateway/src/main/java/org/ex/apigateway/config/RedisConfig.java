package org.ex.apigateway.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.ex.apigateway.model.TenantPolicy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisConfig {

    /**
     * Reactive template, not the blocking RedisTemplate.
     *
     * Tenant policy is read on every request from inside the gateway's filter
     * chain, i.e. on a Netty event-loop thread. The blocking template that used
     * to back this stalled that thread for the duration of the Redis round trip,
     * which quietly capped the whole gateway's throughput at the (small) number
     * of event-loop threads and defeated the point of running WebFlux.
     *
     * The value serializer is bound to TenantPolicy rather than the generic one.
     * GenericJackson2JsonRedisSerializer writes an "@class" field and will
     * instantiate whatever type it finds there on read - meaning anything able
     * to write to Redis could steer deserialization. Pinning the type removes
     * that as a consideration entirely.
     */
    @Bean
    public ReactiveRedisTemplate<String, TenantPolicy> tenantPolicyRedisTemplate(
            ReactiveRedisConnectionFactory factory, ObjectMapper objectMapper) {

        Jackson2JsonRedisSerializer<TenantPolicy> valueSerializer =
                new Jackson2JsonRedisSerializer<>(objectMapper, TenantPolicy.class);

        RedisSerializationContext<String, TenantPolicy> context =
                RedisSerializationContext.<String, TenantPolicy>newSerializationContext(
                                new StringRedisSerializer())
                        .value(valueSerializer)
                        .build();

        return new ReactiveRedisTemplate<>(factory, context);
    }
}
