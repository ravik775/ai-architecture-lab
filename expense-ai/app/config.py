from enum import Enum
from os import getenv
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class LLMImplementation(str, Enum):
    LiteLLM = "LiteLLM"
    MOCKLLM = "MockLLM"

class PipelineSettings(BaseModel):
    policies: list[str] = Field(default_factory=list)


class ProviderSettings(BaseModel):
    name: str
    model: str

    base_url: str | None = None
    api_key: str | None = None

    priority: int = Field(default=100, ge=0, le=100)
    enabled: bool = True

    @model_validator(mode="after")
    def populate_api_key(self):
        self.api_key = self.api_key or getenv(f"{self.name.upper()}_API_KEY")
        return self


class RuntimeSettings(BaseModel):
    implementation:LLMImplementation = LLMImplementation.LiteLLM
    temperature: float = Field(default=0.0, ge=0.0)
    max_tokens: int = Field(default=2000, gt=0)
    timeout_seconds: int = Field(default=30, gt=0)

    stream: bool = False

    max_retries: int = Field(default=3, ge=0)
    retry_backoff: float = Field(default=1.0, gt=0)


class LoggingSettings(BaseModel):
    log_prompts: bool = False
    log_responses: bool = False
    log_token_usage: bool = True
    prompt_preview_chars: int = 300


class ObservabilitySettings(BaseModel):
    tracing_enabled: bool = True
    metrics_enabled: bool = True
    console_metric_exporter_enabled: bool = False
    console_trace_exporter_enabled: bool = False


class CircuitBreakerSettings(BaseModel):
    failure_threshold: int = Field(default=5, gt=0)
    reset_timeout: int = Field(default=60, gt=0)
    success_threshold: int = Field(default=1, gt=0)


class Settings(BaseSettings):
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    providers: list[ProviderSettings] = Field(default_factory=list)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    observability: ObservabilitySettings = Field(
        default_factory=ObservabilitySettings
    )

    circuit_breaker: CircuitBreakerSettings = Field(
        default_factory=CircuitBreakerSettings
    )

    model_config = SettingsConfigDict(
        yaml_file= BASE_DIR / "application.yaml",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type["Settings"],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ):
        return (
            init_settings,
            YamlConfigSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )



settings = Settings()
