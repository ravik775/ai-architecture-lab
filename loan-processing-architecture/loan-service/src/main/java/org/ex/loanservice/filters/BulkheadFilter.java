package org.ex.loanservice.filters;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadRegistry;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
@Order(1)
public class BulkheadFilter extends OncePerRequestFilter {

    private final Bulkhead bulkhead;

    public BulkheadFilter(BulkheadRegistry registry) {
        // Reuses the same "loanServiceBulkhead" instance already defined
        // in application.yml — no new YAML needed.
        this.bulkhead = registry.bulkhead("loanServiceBulkhead");
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        // Health/monitoring traffic shouldn't compete with business traffic
        // for the same 10 concurrent slots.
        return path.startsWith("/actuator");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                     HttpServletResponse response,
                                     FilterChain filterChain) throws ServletException, IOException {

        if (!bulkhead.tryAcquirePermission()) {
            response.setStatus(HttpServletResponse.SC_SERVICE_UNAVAILABLE);
            response.setHeader("Retry-After", "1");
            response.getWriter().write(
                "This instance is at capacity (10 concurrent requests). Please retry shortly.");
            return;
        }

        try {
            filterChain.doFilter(request, response);
        } finally {
            bulkhead.onComplete();
        }
    }
}