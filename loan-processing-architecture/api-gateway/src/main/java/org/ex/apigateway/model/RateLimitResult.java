package org.ex.apigateway.config;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class RateLimitResult {

    private boolean allowed;

    private long limit;

    private long remaining;

    private long retryAfterSeconds;

    private boolean approximateRemaining;
}