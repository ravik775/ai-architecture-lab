package org.ex.apigateway.controller;

import org.ex.apigateway.FallbackResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
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
    /**
     * Mapped for ALL HTTP methods, not just GET. The CircuitBreaker filter
     * forwards the original request (verb included) here, so a GET-only
     * mapping turned every tripped POST/PUT/DELETE into a misleading
     * "405 Method Not Allowed" instead of the intended 503.
     */
    @RequestMapping("/fallback/loan-service")
    public Mono<ResponseEntity<FallbackResponse>> loanServiceFallback() {
        FallbackResponse response = new FallbackResponse(
                "LOAN_SERVICE_UNAVAILABLE",
                "Loan service is temporarily unavailable, please try again later.",
                System.currentTimeMillis()
        );
        return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(response));
    }
}