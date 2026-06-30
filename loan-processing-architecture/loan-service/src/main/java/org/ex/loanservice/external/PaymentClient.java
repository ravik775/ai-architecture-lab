package org.ex.loanservice.external;

import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.retry.annotation.Retry;
import io.github.resilience4j.timelimiter.annotation.TimeLimiter;import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

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
    // @TimeLimiter(name = "")
    public String getPayment(Long loanId) {

        return restTemplate.getForObject(
                "http://localhost:8083/payment/" + loanId,
                String.class
        );
    }

    public PaymentResponse fallback(
            Long loanId,
            Exception ex) {

        System.out.println(
                "Fallback Invoked : " + ex.getMessage());

        return new PaymentResponse(
                "FAILED",
                "Payment Service Unavailable"
        );
    }
}