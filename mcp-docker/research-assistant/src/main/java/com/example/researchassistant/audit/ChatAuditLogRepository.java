package com.example.researchassistant.audit;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ChatAuditLogRepository extends JpaRepository<ChatAuditLog, Long> {

    List<ChatAuditLog> findByTenantIdOrderByCreatedAtDesc(String tenantId);
}
