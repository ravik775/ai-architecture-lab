package org.ex.loanservice.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

/**
 * loan-service independently re-validates the JWT - it does NOT trust that
 * api-gateway already did this. Closes the "gateway bypass" STRIDE finding:
 * mTLS (Phase 4) proves which workload is connecting; it says nothing about
 * whether this specific request carries a currently-valid, correctly-scoped
 * token. Both checks must pass independently.
 */
@Configuration
@EnableWebSecurity
public class LoanServiceSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health/**", "/actuator/info").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> {}));
        return http.build();
    }
}