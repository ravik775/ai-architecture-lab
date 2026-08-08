package com.example.researchassistant.audit;

import java.time.Instant;

import org.hibernate.annotations.CreationTimestamp;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "chat_audit_log")
public class ChatAuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 64)
    private String tenantId;

    @Column(name = "user_sub", nullable = false, length = 128)
    private String userSub;

    @Column(name = "question", nullable = false, columnDefinition = "TEXT")
    private String question;

    @Column(name = "answer_snippet", nullable = false, length = 500)
    private String answerSnippet;

    @Column(name = "trace_id", length = 64)
    private String traceId;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected ChatAuditLog() {
        // JPA
    }

    public ChatAuditLog(String tenantId, String userSub, String question, String answerSnippet, String traceId) {
        this.tenantId = tenantId;
        this.userSub = userSub;
        this.question = question;
        this.answerSnippet = answerSnippet;
        this.traceId = traceId;
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getUserSub() {
        return userSub;
    }

    public String getQuestion() {
        return question;
    }

    public String getAnswerSnippet() {
        return answerSnippet;
    }

    public String getTraceId() {
        return traceId;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
