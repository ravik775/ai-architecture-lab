from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    app_name: str = Field(default='ai-agent-gateway', alias='APP_NAME')
    env: str = Field(default='local', alias='ENV')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')

    default_model: str = Field(default='openai/gpt-4o-mini', alias='DEFAULT_MODEL')
    fallback_model: str = Field(default='openai/gpt-4o-mini', alias='FALLBACK_MODEL')
    litellm_api_base: str | None = Field(default=None, alias='LITELLM_API_BASE')

    openai_api_key: str | None = Field(default=None, alias='OPENAI_API_KEY')
    huggingface_api_key: str | None = Field(default=None, alias='HUGGINGFACE_API_KEY')

    request_timeout_seconds: float = Field(default=20.0, alias='REQUEST_TIMEOUT_SECONDS')


@lru_cache
def get_settings() -> Settings:
    return Settings()
