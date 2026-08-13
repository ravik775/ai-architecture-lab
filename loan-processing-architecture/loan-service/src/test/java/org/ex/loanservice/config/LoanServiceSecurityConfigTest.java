package org.ex.loanservice.config;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Isolates the JWT -> GrantedAuthority mapping from the full Spring Security
 * filter chain. This is the exact bug that was found live: Keycloak issues
 * realm roles under a "roles" claim (see realm-export.json's
 * realm-roles-mapper), but Spring Security's default converter looks for
 * "scope"/"scp" - without this custom converter every @PreAuthorize check
 * silently fails closed for every user, regardless of their actual roles.
 */
class LoanServiceSecurityConfigTest {

    private final LoanServiceSecurityConfig config = new LoanServiceSecurityConfig();

    private Jwt jwtWithRoles(List<String> roles) {
        Jwt.Builder builder = Jwt.withTokenValue("token")
                .header("alg", "none")
                .subject("user-id")
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(300));
        if (roles != null) {
            builder.claim("roles", roles);
        }
        return builder.build();
    }

    @Test
    void convert_mapsRolesClaimToRolePrefixedAuthorities() {
        // Scenario: bob's token carries roles=[loan-officer, loan-admin].
        // The converter must produce ROLE_loan-officer and ROLE_loan-admin
        // authorities - the exact prefix Spring's hasRole('loan-admin')
        // expects (hasRole implicitly prepends "ROLE_").
        Jwt bobJwt = jwtWithRoles(List.of("loan-officer", "loan-admin"));

        AbstractAuthenticationToken authentication = config.jwtAuthenticationConverter().convert(bobJwt);

        assertThat(authentication.getAuthorities())
                .extracting(Object::toString)
                .containsExactlyInAnyOrder("ROLE_loan-officer", "ROLE_loan-admin");
    }

    @Test
    void convert_mapsSingleRoleClaim_forOfficerOnlyUser() {
        // Scenario: alice's token carries roles=[loan-officer] only - this
        // is what makes her allowed to submit but forbidden from approving.
        Jwt aliceJwt = jwtWithRoles(List.of("loan-officer"));

        AbstractAuthenticationToken authentication = config.jwtAuthenticationConverter().convert(aliceJwt);

        assertThat(authentication.getAuthorities())
                .extracting(Object::toString)
                .containsExactly("ROLE_loan-officer");
    }

    @Test
    void convert_producesNoAuthorities_whenRolesClaimAbsent() {
        // Scenario: a token with no "roles" claim at all (e.g. a
        // misconfigured client) must not be granted any authority by
        // accident - it should authenticate with zero authorities, which
        // fails every hasRole(...) check rather than passing one open.
        Jwt jwtWithoutRoles = jwtWithRoles(null);

        AbstractAuthenticationToken authentication = config.jwtAuthenticationConverter().convert(jwtWithoutRoles);

        assertThat(authentication.getAuthorities()).isEmpty();
    }
}
