package org.ex.apigateway;

public record FallbackResponse(String errorCode,
                               String message,
                               long timestamp) {
}
