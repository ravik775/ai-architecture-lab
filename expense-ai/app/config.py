import json
import logging
from enum import Enum
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from os import environ, getenv
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


BASE_DIR = Path(__file__).resolve().parent.parent

# ProviderSettings reads provider keys through getenv().
# Existing operating-system/container variables remain higher priority
# because override=False.
load_dotenv(
    BASE_DIR / ".env",
    override=False,
)

config_logger = logging.getLogger("expense_ai")


def database_host(value: str | None) -> str | None:
    """Extract the database hostname without exposing credentials."""
    if not value:
        return None

    return urlparse(value).hostname


def configuration_debug_enabled() -> bool:
    """Return whether configuration-resolution logging is enabled."""
    return getenv("CONFIG_DEBUG", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


DatabaseSSLMode = Literal[
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
]


class LLMImplementation(str, Enum):
    LiteLLM = "LiteLLM"
    MOCKLLM = "MockLLM"


class PipelineSettings(BaseModel):
    policies: list[str] = Field(
        default_factory=list,
    )


class RAGSettings(BaseModel):
    enabled: bool = True

    collection_name: str = Field(
        default="expense_policies",
        max_length=50,
    )

    persist_directory: str = ".chroma"

    top_k: int = Field(
        default=3,
        gt=0,
        le=40,
    )


class ProviderSettings(BaseModel):
    name: str
    model: str

    base_url: str | None = None

    api_key: str | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )

    priority: int = Field(
        default=100,
        ge=0,
        le=100,
    )

    enabled: bool = True

    @model_validator(mode="after")
    def populate_api_key(self):
        self.api_key = (
            self.api_key
            or getenv(f"{self.name.upper()}_API_KEY")
        )

        return self


class RuntimeSettings(BaseModel):
    implementation: LLMImplementation = LLMImplementation.LiteLLM
    temperature: float = Field(default=0.0, ge=0.0, lt=2)
    max_tokens: int = Field(default=2000, gt=0,lt=6000)
    timeout_seconds: int = Field(default=10, gt=0, lt=200)
    include_examples: bool = True
    stream: bool = False
    max_retries: int = Field(default=1, ge=0, lt=5)
    retry_backoff: float = Field(default=1.0, gt=0, lt=6 )


class LoggingSettings(BaseModel):
    log_prompts: bool = False
    log_responses: bool = False
    log_token_usage: bool = True
    prompt_preview_chars: int = 300


class ObservabilitySettings(BaseModel):
    tracing_enabled: bool = True
    metrics_enabled: bool = True
    otlp_exporter_enabled: bool = True
    console_metric_exporter_enabled: bool = False
    console_trace_exporter_enabled: bool = False



class CircuitBreakerSettings(BaseModel):
    failure_threshold: int = Field(
        default=5,
        gt=0,
    )

    reset_timeout: int = Field(
        default=60,
        gt=0,
    )

    success_threshold: int = Field(
        default=1,
        gt=0,
    )


class DataSettings(BaseModel):
    database_url: str | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )

    database_sslmode: DatabaseSSLMode = "prefer"


class Settings(BaseSettings):
    pipeline: PipelineSettings = Field(
        default_factory=PipelineSettings,
    )

    providers: list[ProviderSettings] = Field(
        default_factory=list,
    )

    runtime: RuntimeSettings = Field(
        default_factory=RuntimeSettings,
    )

    logging: LoggingSettings = Field(
        default_factory=LoggingSettings,
    )

    rag: RAGSettings = Field(
        default_factory=RAGSettings,
    )

    data: DataSettings = Field(
        default_factory=DataSettings,
    )

    observability: ObservabilitySettings = Field(
        default_factory=ObservabilitySettings,
    )

    circuit_breaker: CircuitBreakerSettings = Field(
        default_factory=CircuitBreakerSettings,
    )

    agentic_expense: bool = True

    # Flat compatibility variables are normalized into their nested
    # settings objects in normalize_platform_configuration().
    runtime_timeout_seconds: int | None = Field(
        default=None,
        validation_alias="RUNTIME_TIMEOUT_SECONDS",
        gt=0,
        exclude=True,
    )

    runtime_max_retries: int | None = Field(
        default=None,
        validation_alias="RUNTIME_MAX_RETRIES",
        ge=0,
        exclude=True,
    )

    rag_persist_directory: str | None = Field(
        default=None,
        validation_alias="RAG_PERSIST_DIRECTORY",
        exclude=True,
    )

    otel_console_trace_enabled: bool | None = Field(
        default=None,
        validation_alias="OTEL_CONSOLE_TRACE_ENABLED",
        exclude=True,
    )

    model_config = SettingsConfigDict(
        yaml_file=BASE_DIR / "application.yaml",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",

        # DATA__DATABASE_URL becomes:
        # {"data": {"database_url": "..."}}
        env_nested_delimiter="__",

        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    @model_validator(mode="before")
    @classmethod
    def log_database_source_resolution(cls, values):
        """
        Log database configuration resolution without exposing
        usernames, passwords, or complete connection URLs.

        This diagnostic log is enabled only when CONFIG_DEBUG=true.
        """
        if not configuration_debug_enabled():
            return values

        raw_environment_url = getenv("DATA__DATABASE_URL")

        yaml_values = YamlConfigSettingsSource(cls)()
        yaml_data = yaml_values.get("data", {})
        yaml_url = (
            yaml_data.get("database_url")
            if isinstance(yaml_data, dict)
            else None
        )

        merged_url = None

        if isinstance(values, dict):
            merged_data = values.get("data", {})

            if isinstance(merged_data, dict):
                merged_url = merged_data.get("database_url")
            else:
                merged_url = getattr(
                    merged_data,
                    "database_url",
                    None,
                )

        config_logger.warning(
            json.dumps(
                {
                    "event": "config.database.resolution",
                    "database_environment_keys": sorted(
                        key
                        for key in environ
                        if "DATABASE" in key
                        or key.startswith("DATA__")
                    ),
                    "environment_present": bool(
                        raw_environment_url
                    ),
                    "environment_host": database_host(
                        raw_environment_url
                    ),
                    "yaml_host": database_host(yaml_url),
                    "merged_host": database_host(merged_url),
                    "env_nested_delimiter": (
                        cls.model_config.get(
                            "env_nested_delimiter"
                        )
                    ),
                }
            )
        )

        return values

    @model_validator(mode="after")
    def normalize_platform_configuration(self):
        if self.runtime_timeout_seconds is not None:
            self.runtime.timeout_seconds = (
                self.runtime_timeout_seconds
            )

        if self.runtime_max_retries is not None:
            self.runtime.max_retries = (
                self.runtime_max_retries
            )

        if self.rag_persist_directory:
            self.rag.persist_directory = (
                self.rag_persist_directory
            )

        if self.otel_console_trace_enabled is not None:
            self.observability.console_trace_exporter_enabled = (
                self.otel_console_trace_enabled
            )

        if configuration_debug_enabled():
            config_logger.warning(
                json.dumps(
                    {
                        "event": "config.database.final",
                        "final_host": database_host(
                            self.data.database_url
                        ),
                        "sslmode": (
                            self.data.database_sslmode
                        ),
                    }
                )
            )

        if self.agentic_expense and not self.data.database_url:
            raise ValueError(
                "Postgres is required when "
                "AGENTIC_EXPENSE=true. "
                "Set DATA__DATABASE_URL."
            )

        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type["Settings"],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """
        Earlier sources have higher priority.

        Settings(...) arguments
        > operating-system/container environment
        > .env
        > application.yaml
        > secrets directory
        > model defaults
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()