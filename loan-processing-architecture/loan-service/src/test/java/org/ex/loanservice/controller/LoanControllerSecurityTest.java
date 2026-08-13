package org.ex.loanservice.controller;

import org.ex.loanservice.config.LoanServiceSecurityConfig;
import org.ex.loanservice.domain.LoanApplication;
import org.ex.loanservice.domain.LoanStatus;
import org.ex.loanservice.filters.BulkheadFilter;
import org.ex.loanservice.filters.GatewaySpiffeIdentityFilter;
import org.ex.loanservice.service.InvalidLoanStateException;
import org.ex.loanservice.service.LoanApplicationService;
import org.ex.loanservice.service.LoanNotFoundException;
import org.ex.loanservice.service.SubmitResult;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.time.Instant;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Drives the real Spring Security filter chain (LoanServiceSecurityConfig,
 * including the roles-claim JwtAuthenticationConverter and
 * @EnableMethodSecurity) against LoanController's @PreAuthorize
 * annotations. This is the test-level equivalent of what was verified live
 * against the running stack: alice (loan-officer only) can submit but is
 * forbidden from approving; bob (loan-officer + loan-admin) can do both.
 */
@WebMvcTest(
        controllers = LoanController.class,
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = {BulkheadFilter.class, GatewaySpiffeIdentityFilter.class}))
@Import({LoanServiceSecurityConfig.class, LoanExceptionHandler.class})
// This slice tests LoanController's own @PreAuthorize rules in isolation.
// BulkheadFilter (needs a live resilience4j registry) and
// GatewaySpiffeIdentityFilter (needs a real mTLS client cert) are excluded
// deliberately - they're separate concerns with their own infra
// requirements, not part of what this test verifies. Eureka client is
// disabled because the "/actuator/health/**" permitAll matcher otherwise
// pulls in the full actuate health-indicator chain, including
// EurekaHealthIndicator, which needs a resolvable eureka.instance.secure-port
// that only exists in the running Docker Compose stack.
@TestPropertySource(properties = "eureka.client.enabled=false")
class LoanControllerSecurityTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private LoanApplicationService loanApplicationService;

    private static final String LOAN_OFFICER = "ROLE_loan-officer";
    private static final String LOAN_ADMIN = "ROLE_loan-admin";

    private LoanApplication sampleLoan(LoanStatus status) {
        LoanApplication loan = LoanApplication.builder()
                .id("loan-1")
                .applicantName("Carol Test")
                .amount(BigDecimal.valueOf(15000))
                .tenant("tenant-a")
                .submittedBy("alice-id")
                .submittedAt(Instant.now())
                .build();
        if (status == LoanStatus.APPROVED) {
            loan.tryApprove("bob-id", Instant.now());
        }
        return loan;
    }

    @Test
    void submit_returns201_forUserWithLoanOfficerRole() throws Exception {
        // Scenario: alice (loan-officer) submits a loan - allowed.
        when(loanApplicationService.submit(any(), any(), any()))
                .thenReturn(new SubmitResult(sampleLoan(LoanStatus.PENDING), false));

        mockMvc.perform(post("/loan")
                        .with(jwt().authorities(new SimpleGrantedAuthority(LOAN_OFFICER)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"applicantName\":\"Carol Test\",\"amount\":15000}"))
                .andExpect(status().isCreated());
    }

    @Test
    void submit_passesIdempotencyKeyHeaderThrough_andReportsReplayInResponseHeader() throws Exception {
        // Scenario: the controller must forward the Idempotency-Key header to
        // the service and surface the replay outcome back to the caller. Without
        // the Idempotent-Replay header a retrying client cannot distinguish
        // "your retry was deduplicated" from "a new loan was created".
        when(loanApplicationService.submit(any(), any(), eq("key-1")))
                .thenReturn(new SubmitResult(sampleLoan(LoanStatus.PENDING), true));

        mockMvc.perform(post("/loan")
                        .with(jwt().authorities(new SimpleGrantedAuthority(LOAN_OFFICER)))
                        .header("Idempotency-Key", "key-1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"applicantName\":\"Carol Test\",\"amount\":15000}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Idempotent-Replay", "true"));
    }

    @Test
    void submit_withoutIdempotencyKey_reportsNoReplay() throws Exception {
        // Scenario: the header is optional. Omitting it must still work and must
        // report Idempotent-Replay: false rather than omitting the header or
        // failing.
        when(loanApplicationService.submit(any(), any(), isNull()))
                .thenReturn(new SubmitResult(sampleLoan(LoanStatus.PENDING), false));

        mockMvc.perform(post("/loan")
                        .with(jwt().authorities(new SimpleGrantedAuthority(LOAN_OFFICER)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"applicantName\":\"Carol Test\",\"amount\":15000}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Idempotent-Replay", "false"));
    }

    @Test
    void submit_returns403_forUserWithoutLoanOfficerRole() throws Exception {
        // Scenario: an authenticated user who has neither loan-officer nor
        // loan-admin (e.g. a token from an unrelated client) must be denied
        // at the authorization layer before the service method ever runs.
        mockMvc.perform(post("/loan")
                        .with(jwt().authorities(new SimpleGrantedAuthority("ROLE_some-other-role")))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"applicantName\":\"Carol Test\",\"amount\":15000}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void submit_returns401_whenUnauthenticated() throws Exception {
        // Scenario: no bearer token at all - must be rejected before
        // reaching authorization or the controller.
        mockMvc.perform(post("/loan")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"applicantName\":\"Carol Test\",\"amount\":15000}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void submit_returns400_whenApplicantNameBlank() throws Exception {
        // Scenario: @Valid on LoanApplicationRequest must reject a blank
        // applicant name even for a properly authorized loan-officer -
        // authorization passing doesn't mean input validation is skipped.
        mockMvc.perform(post("/loan")
                        .with(jwt().authorities(new SimpleGrantedAuthority(LOAN_OFFICER)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"applicantName\":\"\",\"amount\":15000}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void submit_returns400_whenAmountNotPositive() throws Exception {
        // Scenario: @DecimalMin(0.01) must reject a zero/negative amount.
        mockMvc.perform(post("/loan")
                        .with(jwt().authorities(new SimpleGrantedAuthority(LOAN_OFFICER)))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"applicantName\":\"Carol Test\",\"amount\":0}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void approve_returns200_forUserWithLoanAdminRole() throws Exception {
        // Scenario: bob (loan-officer + loan-admin) approves - allowed.
        // This is the "bob can do both" half of the demo's core assertion.
        when(loanApplicationService.approve(anyString(), any())).thenReturn(sampleLoan(LoanStatus.APPROVED));

        mockMvc.perform(post("/loan/loan-1/approve")
                        .with(jwt().authorities(
                                new SimpleGrantedAuthority(LOAN_OFFICER),
                                new SimpleGrantedAuthority(LOAN_ADMIN))))
                .andExpect(status().isOk());
    }

    @Test
    void approve_returns403_forUserWithOnlyLoanOfficerRole() throws Exception {
        // Scenario: alice (loan-officer only, no loan-admin) attempts to
        // approve - this is THE core RBAC assertion the whole demo exists
        // to prove: having loan-officer must never be sufficient to
        // approve. Verified live against the running stack as an actual
        // HTTP 403 from api-gateway -> loan-service; this test pins the
        // same behavior at the unit level so it can't regress silently.
        mockMvc.perform(post("/loan/loan-1/approve")
                        .with(jwt().authorities(new SimpleGrantedAuthority(LOAN_OFFICER))))
                .andExpect(status().isForbidden());
    }

    @Test
    void approve_returns403_forAuthenticatedUserWithNoRolesAtAll() throws Exception {
        // Scenario: a validly-signed token with an empty/missing roles
        // claim (see LoanServiceSecurityConfigTest) must not default to
        // "allowed" - authentication succeeding is not authorization.
        mockMvc.perform(post("/loan/loan-1/approve").with(jwt()))
                .andExpect(status().isForbidden());
    }

    @Test
    void approve_returns404_whenServiceReportsLoanNotFound() throws Exception {
        // Scenario: an authorized admin approves an id that doesn't exist -
        // LoanExceptionHandler must translate the service's
        // LoanNotFoundException into 404, not a raw 500.
        when(loanApplicationService.approve(anyString(), any()))
                .thenThrow(new LoanNotFoundException("missing-id"));

        mockMvc.perform(post("/loan/missing-id/approve")
                        .with(jwt().authorities(new SimpleGrantedAuthority(LOAN_ADMIN))))
                .andExpect(status().isNotFound());
    }

    @Test
    void approve_returns409_whenServiceReportsAlreadyApproved() throws Exception {
        // Scenario: an authorized admin re-approves an already-APPROVED
        // loan - must surface as 409 Conflict, not 500 or a silent no-op.
        when(loanApplicationService.approve(anyString(), any()))
                .thenThrow(new InvalidLoanStateException("loan-1", LoanStatus.APPROVED));

        mockMvc.perform(post("/loan/loan-1/approve")
                        .with(jwt().authorities(new SimpleGrantedAuthority(LOAN_ADMIN))))
                .andExpect(status().isConflict());
    }

    @Test
    void get_returns200_forAnyAuthenticatedUser_regardlessOfRole() throws Exception {
        // Scenario: reading a loan's status has no @PreAuthorize role check
        // by design - any authenticated caller (officer or admin) can view
        // it, unlike submit/approve which are role-gated.
        when(loanApplicationService.get(anyString(), any())).thenReturn(sampleLoan(LoanStatus.PENDING));

        mockMvc.perform(get("/loan/loan-1")
                        .with(jwt().authorities(new SimpleGrantedAuthority(LOAN_OFFICER))))
                .andExpect(status().isOk());
    }

    @Test
    void get_returns401_whenUnauthenticated() throws Exception {
        // Scenario: even the read-only endpoint requires a valid token -
        // "anyRequest().authenticated()" applies to everything except the
        // explicitly permitted actuator health/info paths.
        mockMvc.perform(get("/loan/loan-1"))
                .andExpect(status().isUnauthorized());
    }
}
