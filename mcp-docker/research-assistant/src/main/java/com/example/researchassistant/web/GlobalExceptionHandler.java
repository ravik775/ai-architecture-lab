package com.example.researchassistant.web;

import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeoutException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import com.example.researchassistant.security.MissingTenantClaimException;
import com.example.researchassistant.web.dto.ErrorResponse;

import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.ratelimiter.RequestNotPermitted;

/**
 * The four Resilience4j patterns wrapping ResearchAssistantService.answer() throw
 * distinct exception types on rejection; this is the single place that maps each to
 * the HTTP status a caller should actually act on, instead of scattering fallback
 * methods across the service. Async controller methods that fail asynchronously
 * surface here wrapped in CompletionException, so that case is unwrapped first.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(CompletionException.class)
    public ResponseEntity<ErrorResponse> handleCompletion(CompletionException ex) {
        Throwable cause = ex.getCause() != null ? ex.getCause() : ex;
        return handleByType(cause);
    }

    @ExceptionHandler(RequestNotPermitted.class)
    public ResponseEntity<ErrorResponse> handleRateLimit(RequestNotPermitted ex) {
        return respond(HttpStatus.TOO_MANY_REQUESTS, "rate_limit_exceeded", ex);
    }

    @ExceptionHandler(BulkheadFullException.class)
    public ResponseEntity<ErrorResponse> handleBulkheadFull(BulkheadFullException ex) {
        return respond(HttpStatus.SERVICE_UNAVAILABLE, "too_many_concurrent_requests", ex);
    }

    @ExceptionHandler(CallNotPermittedException.class)
    public ResponseEntity<ErrorResponse> handleCircuitOpen(CallNotPermittedException ex) {
        return respond(HttpStatus.SERVICE_UNAVAILABLE, "downstream_unavailable", ex);
    }

    @ExceptionHandler(TimeoutException.class)
    public ResponseEntity<ErrorResponse> handleTimeout(TimeoutException ex) {
        return respond(HttpStatus.GATEWAY_TIMEOUT, "downstream_timeout", ex);
    }

    @ExceptionHandler(MissingTenantClaimException.class)
    public ResponseEntity<ErrorResponse> handleMissingTenant(MissingTenantClaimException ex) {
        return respond(HttpStatus.FORBIDDEN, "invalid_token_claims", ex);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException ex) {
        String message = ex.getBindingResult().getFieldErrors().stream()
            .findFirst()
            .map(fe -> fe.getField() + " " + fe.getDefaultMessage())
            .orElse("invalid request");
        return respond(HttpStatus.BAD_REQUEST, "validation_failed", message);
    }

    private ResponseEntity<ErrorResponse> handleByType(Throwable ex) {
        if (ex instanceof RequestNotPermitted e) {
            return handleRateLimit(e);
        }
        if (ex instanceof BulkheadFullException e) {
            return handleBulkheadFull(e);
        }
        if (ex instanceof CallNotPermittedException e) {
            return handleCircuitOpen(e);
        }
        if (ex instanceof TimeoutException e) {
            return handleTimeout(e);
        }
        log.error("Unhandled async exception", ex);
        return respond(HttpStatus.INTERNAL_SERVER_ERROR, "internal_error", "an unexpected error occurred");
    }

    private ResponseEntity<ErrorResponse> respond(HttpStatus status, String code, Throwable ex) {
        return respond(status, code, ex.getMessage());
    }

    private ResponseEntity<ErrorResponse> respond(HttpStatus status, String code, String message) {
        log.warn("{}: {}", code, message);
        return ResponseEntity.status(status).body(new ErrorResponse(code, message));
    }
}
