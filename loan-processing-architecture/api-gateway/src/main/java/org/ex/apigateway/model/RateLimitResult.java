package org.ex.apigateway.model;
import lombok.Builder;

@Builder
public record RateLimitResult(
        boolean allowed,
        long limit,
        long remaining,
        long retryAfterSeconds,
        boolean approximateRemaining
) {
}