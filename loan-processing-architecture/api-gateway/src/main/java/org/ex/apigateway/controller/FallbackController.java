package org.ex.apigateway.controller;

import org.ex.apigateway.FallbackResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class FallbackController {

    /**
     * Reactive corollary of the webflux switch: with no MVC DispatcherServlet
     * on the classpath, an @RestController must return Mono/Flux (or plain
     * values, which Spring resolves via WebFlux's functional/annotated
     * handler support) rather than block on ResponseEntity construction.
     */
    @GetMapping("/fallback/loan-service")
    public Mono<ResponseEntity<FallbackResponse>> loanServiceFallback() {
        FallbackResponse response = new FallbackResponse(
                "LOAN_SERVICE_UNAVAILABLE",
                "Loan service is temporarily unavailable, please try again later.",
                System.currentTimeMillis()
        );
        return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(response));
    }
}