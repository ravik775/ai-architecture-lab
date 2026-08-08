package com.example.researchassistant.service;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.mcp.SyncMcpToolCallbackProvider;
import org.springframework.stereotype.Service;

import com.example.researchassistant.audit.ChatAuditLog;
import com.example.researchassistant.audit.ChatAuditLogRepository;

import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;
import io.github.resilience4j.timelimiter.annotation.TimeLimiter;
import io.micrometer.context.ContextExecutorService;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.tracing.Tracer;
import jakarta.annotation.PreDestroy;

/**
 * Everything downstream of the HTTP boundary — the LLM call and any MCP tool
 * round-trips it triggers — is wrapped as ONE resilience unit rather than one breaker
 * per hop. Spring AI's ChatClient runs its tool-execution loop internally, so there is
 * no clean seam to wrap "just the MCP call" without re-implementing that loop
 * ourselves; from this service's point of view, "the model is slow" and "the MCP
 * Gateway is unreachable" fail the same way, so a single boundary around the whole
 * exchange gives real protection without inventing complexity Spring AI doesn't expose
 * a seam for. See ARCHITECTURE.md for the full rationale.
 */
@Service
public class ResearchAssistantService {

    private static final int MAX_ANSWER_SNIPPET_LENGTH = 500;

    private final ChatClient chatClient;
    private final SyncMcpToolCallbackProvider toolCallbackProvider;
    private final ChatAuditLogRepository auditLogRepository;
    private final Tracer tracer;
    private final ExecutorService chatExecutor;

    public ResearchAssistantService(ChatClient chatClient,
                                     SyncMcpToolCallbackProvider toolCallbackProvider,
                                     ChatAuditLogRepository auditLogRepository,
                                     Tracer tracer) {
        this.chatClient = chatClient;
        this.toolCallbackProvider = toolCallbackProvider;
        this.auditLogRepository = auditLogRepository;
        this.tracer = tracer;
        // Wrapped so the tracing span active on the HTTP thread is still "current"
        // inside this async task — otherwise the MCP/LLM calls made here would show up
        // as a disconnected trace instead of a child span of the original request.
        this.chatExecutor = ContextExecutorService.wrap(
            Executors.newFixedThreadPool(8),
            ContextSnapshotFactory.builder().build());
    }

    @RateLimiter(name = "chat")
    @Bulkhead(name = "chat")
    @CircuitBreaker(name = "chat")
    @TimeLimiter(name = "chat")
    public CompletableFuture<String> answer(String question, String tenantId, String userSub) {
        return CompletableFuture.supplyAsync(() -> {
            String content = chatClient.prompt()
                .user(question)
                .toolCallbacks(toolCallbackProvider.getToolCallbacks())
                .call()
                .content();
            persistAudit(tenantId, userSub, question, content);
            return content;
        }, chatExecutor);
    }

    private void persistAudit(String tenantId, String userSub, String question, String answer) {
        String traceId = tracer.currentSpan() != null
            ? tracer.currentSpan().context().traceId()
            : null;
        String snippet = answer.length() > MAX_ANSWER_SNIPPET_LENGTH
            ? answer.substring(0, MAX_ANSWER_SNIPPET_LENGTH)
            : answer;
        auditLogRepository.save(new ChatAuditLog(tenantId, userSub, question, snippet, traceId));
    }

    @PreDestroy
    void shutdown() {
        chatExecutor.shutdown();
    }
}
