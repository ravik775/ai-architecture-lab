package com.example.researchassistant.web;

import java.util.List;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.researchassistant.audit.ChatAuditLogRepository;
import com.example.researchassistant.security.AuthenticatedUser;
import com.example.researchassistant.web.dto.AuditEntryResponse;

/**
 * Deliberately scoped to "my tenant's history" only — there is no cross-tenant admin
 * view in this use case. Row-level filtering by tenant_id is the whole point being
 * demonstrated here; a broader admin view is a separate, later concern.
 */
@RestController
@RequestMapping("/api")
public class AuditController {

    private final ChatAuditLogRepository repository;

    public AuditController(ChatAuditLogRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/audit")
    public List<AuditEntryResponse> myTenantAuditLog(@AuthenticationPrincipal Jwt jwt) {
        AuthenticatedUser user = AuthenticatedUser.from(jwt);
        return repository.findByTenantIdOrderByCreatedAtDesc(user.tenantId())
            .stream()
            .map(AuditEntryResponse::from)
            .toList();
    }
}
