from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel
from enum import Enum
import os
class Providers(str, Enum):
    MOCK = "mock"
    LITELLM = "litellm"

class AISettings(BaseModel):
    llm_provider: Providers = Providers.LITELLM
    llm_model: str = "ollama_chat/llama3.2:3b"
    model_base_url: str = "http://localhost:11434"
    model_api_key: str | None = None
    temperature: int = 0
    max_tokens: int | None = 200
    timeout: int = 36000
    stream: bool = False
    max_retries: int = 3
    retry_backoff: float = 1.0

class Logging(BaseModel):
    log_prompts: bool = True
    log_responses: bool = False
    log_token_usage: bool = True


class IntegrationSettings(BaseModel):
    huggingface_api_key: str | None = None
    github_token: str | None = None

class Settings(BaseSettings):
    environment: str = "dev"
    ai: AISettings = AISettings()
    integration: IntegrationSettings = IntegrationSettings()

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="."  # <--- This allows using dots for nesting
    )


settings = Settings()