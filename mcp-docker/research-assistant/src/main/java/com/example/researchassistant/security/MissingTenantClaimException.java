package com.example.researchassistant.security;

public class MissingTenantClaimException extends RuntimeException {

    public MissingTenantClaimException() {
        super("JWT is missing the required 'tenant_id' claim");
    }
}
