package org.ex.loanservice.config;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.data.redis.RedisProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.StringUtils;

@Slf4j
@Configuration
@RequiredArgsConstructor
public class RedisConfigLogger {

    private final RedisProperties redisProperties;

    @Bean
    ApplicationRunner printRedisConfig() {
        return args -> log.debug(
                "Redis config: host={}, port={}, username={}, passwordSet={}, passwordLength={}, database={}, timeout={}",
                redisProperties.getHost(),
                redisProperties.getPort(),
                redisProperties.getUsername(),
                StringUtils.hasText(redisProperties.getPassword()),
                redisProperties.getPassword() == null ? 0 : redisProperties.getPassword().length(),
                redisProperties.getDatabase(),
                redisProperties.getTimeout()
        );
    }
}