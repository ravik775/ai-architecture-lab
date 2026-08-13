package org.ex.loanservice.external;

import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.retry.annotation.Retry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

/**
 * Calls a "payment-service" that is not actually deployed in this demo
 * (see docker-compose.yml) - on purpose. Resolving it through Eureka
 * (RestTemplateConfig's bean is @LoadBalanced) means every call fails fast
 * with "no instances available", which is exactly what exercises the
 * retry/bulkhead/circuit-breaker stack below instead of leaving it decorative.
 */
@Slf4j
@Service
public class PaymentClient {

    private final RestTemplate restTemplate;

    public PaymentClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @Bulkhead(
            name = "paymentBulkhead",
            fallbackMethod = "fallback")
    @Retry(
            name = "paymentRetry",
            fallbackMethod = "fallback")
    @CircuitBreaker(
            name = "paymentCircuitBreaker",
            fallbackMethod = "fallback")
    public PaymentResponse getPayment(Long loanId) {

        return restTemplate.getForObject(
                "http://payment-service/payment/" + loanId,
                PaymentResponse.class
        );
    }

    /**
     * Return type must be assignable to getPayment()'s (PaymentResponse) or
     * Resilience4j cannot resolve this as a matching fallback and the
     * original exception propagates instead of ever reaching this method.
     */
    public PaymentResponse fallback(
            Long loanId,
            Exception ex) {

        log.warn("Payment service call failed for loanId={}: {}", loanId, ex.getMessage());

        return new PaymentResponse(
                "FAILED",
                "Payment Service Unavailable"
        );
    }
}