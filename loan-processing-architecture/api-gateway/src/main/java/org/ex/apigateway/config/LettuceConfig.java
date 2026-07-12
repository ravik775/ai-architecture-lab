package org.ex.apigateway.config;

import io.lettuce.core.RedisClient;
import io.lettuce.core.codec.ByteArrayCodec;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.codec.RedisCodec;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.data.redis.RedisProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@Slf4j
public class LettuceConfig {

    @Bean(destroyMethod = "shutdown")
    public RedisClient redisClient(RedisProperties redisProperties) {
        log.debug("Redis Configuration:");
        log.debug("Host             : {}", redisProperties.getHost());
        log.debug("Port             : {}", redisProperties.getPort());
        log.debug("Username         : {}", redisProperties.getUsername());
        log.debug("Password Present : {}", redisProperties.getPassword() != null ? "Yes" : "No");
        log.debug("Database         : {}", redisProperties.getDatabase());
        log.debug("Timeout          : {}", redisProperties.getTimeout());

        if (redisProperties.getLettuce() != null) {
            log.debug("Lettuce Pool Max Active : {}",
                    redisProperties.getLettuce().getPool().getMaxActive());
            log.debug("Lettuce Pool Max Idle   : {}",
                    redisProperties.getLettuce().getPool().getMaxIdle());
            log.debug("Lettuce Pool Min Idle   : {}",
                    redisProperties.getLettuce().getPool().getMinIdle());
            log.debug("Lettuce Pool Max Wait   : {}",
                    redisProperties.getLettuce().getPool().getMaxWait());
        }

        if (redisProperties.getCluster() != null) {
            log.debug("Cluster Nodes    : {}", redisProperties.getCluster().getNodes());
            log.debug("Max Redirects    : {}", redisProperties.getCluster().getMaxRedirects());
        }

        if (redisProperties.getSentinel() != null) {
            log.debug("Sentinel Master  : {}", redisProperties.getSentinel().getMaster());
            log.debug("Sentinel Nodes   : {}", redisProperties.getSentinel().getNodes());
        }

        return RedisClient.create(
                "redis://" +
                        redisProperties.getHost() +
                        ":" +
                        redisProperties.getPort());
    }

    @Bean(destroyMethod = "close")
    public StatefulRedisConnection<String, byte[]> redisConnection(
            RedisClient redisClient) {
        RedisCodec<String, byte[]> codec =
                RedisCodec.of(
                        io.lettuce.core.codec.StringCodec.UTF8,
                        io.lettuce.core.codec.ByteArrayCodec.INSTANCE);
        return redisClient.connect(codec);//ByteArrayCodec.INSTANCE);
    }
}