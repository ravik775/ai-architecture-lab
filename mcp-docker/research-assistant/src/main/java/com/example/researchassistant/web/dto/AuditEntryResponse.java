package com.example.researchassistant.web.dto;

import java.time.Instant;

import com.example.researchassistant.audit.ChatAuditLog;

public record AuditEntryResponse(
    Long id,
    String userSub,
    String question,
    String answerSnippet,
    String traceId,
    Instant createdAt
) {

    public static AuditEntryResponse from(ChatAuditLog entry) {
        return new AuditEntryResponse(
            entry.getId(),
            entry.getUserSub(),
            entry.getQuestion(),
            entry.getAnswerSnippet(),
            entry.getTraceId(),
            entry.getCreatedAt());
    }
}
