package com.example.researchassistant.web;

import java.util.concurrent.CompletableFuture;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.example.researchassistant.security.AuthenticatedUser;
import com.example.researchassistant.service.ResearchAssistantService;
import com.example.researchassistant.web.dto.ChatRequest;
import com.example.researchassistant.web.dto.ChatResponse;

import jakarta.validation.Valid;

@RestController
@RequestMapping("/api")
public class ChatController {

    private final ResearchAssistantService service;

    public ChatController(ResearchAssistantService service) {
        this.service = service;
    }

    @PostMapping("/chat")
    public CompletableFuture<ChatResponse> chat(@Valid @RequestBody ChatRequest request,
                                                 @AuthenticationPrincipal Jwt jwt) {
        AuthenticatedUser user = AuthenticatedUser.from(jwt);
        return service.answer(request.question(), user.tenantId(), user.subject())
            .thenApply(ChatResponse::new);
    }
}
