package org.ex.apigateway.config;

import lombok.extern.slf4j.Slf4j;
import org.ex.apigateway.model.RateLimitResult;
import org.ex.apigateway.service.TenantLeaseService;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.HandlerFilterFunction;
import org.springframework.web.servlet.function.ServerResponse;

@Slf4j
@Component
public class TenantFilterFunctions {

    private static TenantLeaseService leaseService;

    public TenantFilterFunctions(TenantLeaseService leaseService) {
        TenantFilterFunctions.leaseService = leaseService;
    }

    public static HandlerFilterFunction<ServerResponse, ServerResponse> tenantRateLimiter() {

        return (request, next) -> {
            String tenantId = request.headers().firstHeader("X-Tenant-Id");
            if (tenantId == null || tenantId.isBlank())
                tenantId = "Guest";

            RateLimitResult result = leaseService.consume(tenantId);
            log.info("Tenant={} allowed={} remaining={} retryAfter={}", tenantId, result.allowed(), result.remaining(), result.retryAfterSeconds());
            if (!result.allowed()) {
                return ServerResponse.status(HttpStatus.TOO_MANY_REQUESTS)
                        .header("X-RateLimit-Limit", String.valueOf(result.limit()))
                        .header("X-RateLimit-Remaining","0")
                        .header("X-RateLimit-Remaining-Approximate", "true")
                        .header("X-RateLimit-Reset", String.valueOf(result.retryAfterSeconds()))
                        .header("Retry-After",String.valueOf(result.retryAfterSeconds()))
                        .body("Rate limit exceeded for tenant: "+ tenantId);
            }

            ServerResponse response = next.handle(request);
            return response;
            /*return ServerResponse.from(response)
                    .header("X-RateLimit-Limit", String.valueOf(result.limit()))
                    .header("X-RateLimit-Remaining", String.valueOf(result.remaining()))
                    .header("X-RateLimit-Remaining-Approximate","true")
                    .header("X-RateLimit-Reset","0")
                    .build();*/
        };
    }
}