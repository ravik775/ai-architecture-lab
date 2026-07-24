from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
class Settings(BaseSettings):
    environment: str = "dev"
    provider: str = "litellm"
    model: str = "ollama_chat/llama3.2:3b"
    model_base_url: str = "http://localhost:11434"
    model_api_key: str | None = None
    temperature: int = 0
    max_tokens: int|None = 200
    timeout: int = 2400

    huggingface_api_key: str | None = None

    github_token: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()