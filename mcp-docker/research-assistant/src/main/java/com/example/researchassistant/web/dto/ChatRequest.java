package com.example.researchassistant.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ChatRequest(
    @NotBlank
    @Size(max = 2000, message = "question must be 2000 characters or fewer")
    String question
) {
}
