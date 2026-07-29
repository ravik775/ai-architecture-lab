class LLMProviderError(Exception):
    pass

class LLMAuthenticationError(Exception):
    pass

class LLMConnectionError(Exception):
    pass

class LLMTimeoutError(Exception):
    pass

class LLMError(Exception):
    pass

class GuardrailViolation(Exception):
    pass