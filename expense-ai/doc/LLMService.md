# LiteLLMService

## Responsibility

`LiteLLMService` is the infrastructure implementation of the `LLMService` interface. Its responsibility is to:

* Read AI configuration from `Settings`.
* Invoke the LiteLLM SDK.
* Handle provider-specific details (OpenAI, Ollama, OpenRouter, Hugging Face, etc.).
* Translate LiteLLM exceptions into application-level exceptions.
* Return plain text (or a domain-specific response object in later modules) to the business layer.

## Design Principles

* Business services must **never** import or call LiteLLM directly.
* All provider-specific configuration belongs in `LiteLLMService`.
* `ExpenseService` communicates only through the `LLMService` abstraction.
* Switching providers should require only configuration changes, not business logic changes.

## Architecture

```text
ExpenseService
      │
LLMService (Interface)
      │
LiteLLMService
      │
LiteLLM SDK
      │
Inference Provider
(OpenAI / Ollama / OpenRouter / Hugging Face)
```

## Acceptance Criteria

* Reads all AI settings from `Settings`.
* Calls `litellm.completion()`.
* Supports multiple providers through configuration.
* Handles provider exceptions gracefully.
* Returns a provider-agnostic result to the application.
