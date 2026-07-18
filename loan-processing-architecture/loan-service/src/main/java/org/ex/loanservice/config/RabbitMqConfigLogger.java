package org.ex.loanservice.config;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.amqp.RabbitProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.StringUtils;

@Slf4j
@Configuration
@RequiredArgsConstructor
public class RabbitMqConfigLogger {

    private final RabbitProperties rabbitProperties;

    @Bean
    ApplicationRunner printRabbitMqConfig() {
        return args -> log.debug(
                "RabbitMQ config: host={}, port={}, username={}, passwordSet={}, virtualHost={}, addresses={}",
                rabbitProperties.getHost(),
                rabbitProperties.getPort(),
                rabbitProperties.getUsername(),
                StringUtils.hasText(rabbitProperties.getPassword()),
                rabbitProperties.getVirtualHost(),
                rabbitProperties.getAddresses()
        );
    }
}