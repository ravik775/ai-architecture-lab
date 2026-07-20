package org.ex.loanservice.filters;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;

@Slf4j
@Component
@Order(0)
public class GatewaySpiffeIdentityFilter extends OncePerRequestFilter {

    private static final String EXPECTED_GATEWAY_SPIFFE_ID =
            "spiffe://example.org/ns/loan/sa/api-gateway";

    private static final String INTERNAL_TENANT_HEADER = "X-Internal-Tenant-Id";

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return request.getRequestURI().startsWith("/actuator");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {

        X509Certificate[] certificates = getClientCertificates(request);

        if (certificates == null || certificates.length == 0) {
            log.warn("Rejected request without client certificate: path={}", request.getRequestURI());
            response.sendError(HttpServletResponse.SC_FORBIDDEN, "Client certificate required");
            return;
        }

        X509Certificate clientCertificate = certificates[0];

        if (!hasExpectedSpiffeId(clientCertificate, EXPECTED_GATEWAY_SPIFFE_ID)) {
            log.warn("Rejected request from unexpected SPIFFE identity: subject={}",
                    clientCertificate.getSubjectX500Principal());
            response.sendError(HttpServletResponse.SC_FORBIDDEN, "Invalid caller SPIFFE identity");
            return;
        }

        String tenantId = request.getHeader(INTERNAL_TENANT_HEADER);

        log.info("Accepted mTLS request from gatewaySpiffeId={}, tenant={}, path={}",
                EXPECTED_GATEWAY_SPIFFE_ID,
                tenantId,
                request.getRequestURI());

        filterChain.doFilter(request, response);
    }

    private X509Certificate[] getClientCertificates(HttpServletRequest request) {
        Object jakartaCerts = request.getAttribute("jakarta.servlet.request.X509Certificate");
        if (jakartaCerts instanceof X509Certificate[] certs) {
            return certs;
        }

        Object javaxCerts = request.getAttribute("javax.servlet.request.X509Certificate");
        if (javaxCerts instanceof X509Certificate[] certs) {
            return certs;
        }

        return null;
    }

    private boolean hasExpectedSpiffeId(X509Certificate certificate, String expectedSpiffeId) {
        try {
            Collection<List<?>> subjectAlternativeNames = certificate.getSubjectAlternativeNames();

            if (subjectAlternativeNames == null) {
                return false;
            }

            for (List<?> san : subjectAlternativeNames) {
                if (san.size() < 2) {
                    continue;
                }

                Object type = san.get(0);
                Object value = san.get(1);

                // SAN type 6 = URI SAN
                if (Integer.valueOf(6).equals(type) && expectedSpiffeId.equals(value)) {
                    return true;
                }
            }

            return false;
        } catch (CertificateParsingException ex) {
            log.warn("Could not parse client certificate SAN", ex);
            return false;
        }
    }
}