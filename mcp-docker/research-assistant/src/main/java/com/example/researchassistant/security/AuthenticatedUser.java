package com.example.researchassistant.security;

import org.springframework.security.oauth2.jwt.Jwt;

/**
 * tenant_id is a custom claim populated by a Keycloak protocol mapper (see
 * keycloak/realm-export.json). Its absence means the token was issued outside the
 * expected realm/client setup, so callers treat that as a hard failure rather than
 * falling back to a default tenant.
 */
public record AuthenticatedUser(String subject, String tenantId) {

    public static AuthenticatedUser from(Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tenant_id");
        if (tenantId == null || tenantId.isBlank()) {
            throw new MissingTenantClaimException();
        }
        return new AuthenticatedUser(jwt.getSubject(), tenantId);
    }
}
