"""Application configuration.

All settings are environment-driven via pydantic-settings, using `__` as the
nested delimiter (e.g. `DATABASE__URL`, `AGENT__MODEL_ALIAS`). Defaults are
safe for local/demo use; production values must come from the environment,
never from committed files.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    url: str = "sqlite+aiosqlite:///./data/weather.db"
    busy_timeout_ms: int = 5000
    echo: bool = False


class CacheSettings(BaseModel):
    current_weather_ttl_seconds: float = 30.0
    max_entries: int = 512


class HttpClientSettings(BaseModel):
    connect_timeout_seconds: float = 2.0
    read_timeout_seconds: float = 3.0
    write_timeout_seconds: float = 2.0
    pool_timeout_seconds: float = 2.0
    max_connections: int = 50
    max_keepalive_connections: int = 20
    http2: bool = True
    max_retries: int = 2
    backoff_base_seconds: float = 0.2
    backoff_max_seconds: float = 2.0
    total_latency_budget_seconds: float = 4.0


class WeatherProviderSettings(BaseModel):
    # Corrected during Phase 2 against live Open-Meteo docs: MeteoSwiss is
    # NOT a separate base URL. It's the same /v1/forecast endpoint with
    # models=meteoswiss_icon_seamless (verified via open-meteo.com/en/docs
    # and open-meteo.com/en/docs/meteoswiss-api).
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    # NOTE: "auto" is NOT a valid value despite some Open-Meteo docs
    # summaries implying it is - confirmed via live API response:
    # {"error":true,"reason":"Data corrupted at path ''. Cannot
    # initialize MultiDomains from invalid String value auto."} Omitting
    # `models` entirely gives the same "combine best models" behavior;
    # "best_match" is the verified-working explicit alias for it.
    general_model_selector: str = "best_match"
    meteoswiss_model_selector: str = "meteoswiss_icon_seamless"
    # ICON-CH1/CH2 model domain is documented only as "Central Europe"
    # centered on Switzerland (no published bounding box) - this is an
    # approximation covering Switzerland + Liechtenstein with margin.
    # Config-driven and deliberately conservative: see architecture notes
    # on never silently using MeteoSwiss outside its supported area.
    meteoswiss_lat_min: float = 45.7
    meteoswiss_lat_max: float = 47.9
    meteoswiss_lon_min: float = 5.9
    meteoswiss_lon_max: float = 10.6
    batch_group_concurrency: int = 5


class AgentSettings(BaseModel):
    litellm_base_url: str = "http://localhost:4000"
    litellm_api_key: str = "sk-local-virtual-key"
    model_alias: str = "weather-agent"
    fallback_model_alias: str = "weather-agent-fallback"
    temperature: float = 0.2
    max_output_tokens: int = 800
    request_timeout_seconds: float = 20.0
    total_latency_budget_seconds: float = 25.0


class SchedulerSettings(BaseModel):
    enabled: bool = True
    misfire_grace_time_seconds: int = 3600
    batch_concurrency: int = 5
    # Minute-granularity cron trigger checked every location's local time
    # against its own IANA timezone; see scheduler/jobs.py.
    check_interval_minutes: int = 15
    manual_trigger_enabled: bool = True
    # A "running" job older than this is treated as abandoned (crashed
    # process) rather than a real overlap, and no longer blocks new runs.
    stale_run_timeout_seconds: int = 7200


class SecuritySettings(BaseModel):
    internal_api_token: str = "change-me-internal-token"
    allow_direct_coordinates: bool = True
    # IP-based token-bucket, see app/security/rate_limit.py. Enabled by
    # default now that it's implemented (mirrors metrics_server_enabled's
    # pattern of "on by default, tests opt out" - see conftest.py).
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 10
    max_history_range_days: int = 92
    max_page_size: int = 100
    max_request_body_bytes: int = 16_384
    # Demo-grade JWT auth (see app/security/jwt_tokens.py) - HS256 shared
    # secret, no rotation/revocation. Change before anything but local demo use.
    jwt_secret: str = "change-me-jwt-secret-at-least-32-bytes-long"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60
    # Only a caller whose JWT carries this role may use the force_trace
    # override (see app/observability/sampling.py).
    force_trace_role: str = "trace_admin"
    # Optional bootstrap user, created once at startup if both username and
    # password are set (unset by default - no default user exists unless
    # an operator opts in, deliberately avoiding a known backdoor account).
    # Idempotent: if the username already exists, startup silently skips
    # it rather than erroring or resetting the password - see
    # AuthService.bootstrap_default_user().
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_role: str = "trace_admin"
    # NiceGUI's `app.storage.user` (session state: the login token, and the
    # Correlation ID / Trace-checkbox UI prefs - see app/ui/pages.py) is a
    # server-side dict keyed by a signed browser cookie; this secret signs
    # that cookie. Distinct from jwt_secret - rotating one doesn't affect
    # the other.
    ui_storage_secret: str = "change-me-ui-storage-secret-at-least-32-bytes"


class ObservabilitySettings(BaseModel):
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_enabled: bool = True
    # NOTE: there is deliberately no app-side "sampling ratio" setting for
    # ordinary traffic. The SDK forwards every non-health-check span to the
    # collector (ParentBased(ALWAYS_ON) - see tracing.py's module
    # docstring), because "sample successes at X%, keep all failures" can
    # only be decided after a trace completes - the OTel Collector's
    # tail_sampling processor (docker/otel-collector-config.yaml) makes
    # that call, configured via the top-level (non-app) env var
    # OTEL_TAIL_SAMPLING_BASELINE_PERCENT in .env, not through this class.
    service_name: str = "weather-intelligence-agent"
    metrics_export_interval_seconds: int = 15
    console_export: bool = False
    # /health/live and /health/ready are polled far more often than real
    # traffic and carry little diagnostic value per-call - rate-limited to
    # at most one sampled trace per this many seconds. Set to 60 for a
    # tighter window during active debugging; a caller can always force one
    # specific request through regardless, via the `baggage: force_trace=true`
    # request header - see app/observability/sampling.py.
    health_check_sample_interval_seconds: float = 300.0
    # /metrics is served on its OWN port via prometheus_client's own HTTP
    # server, deliberately separate from the main app port (8000) - so it
    # can be firewalled to internal-only access (e.g. left off
    # docker-compose's published ports, reachable only by other containers
    # on the same Docker network such as Prometheus) without touching the
    # public-facing API/UI port at all. 9464 is OTel's documented
    # conventional default port for a Prometheus exporter.
    metrics_port: int = 9464
    metrics_bind_host: str = "0.0.0.0"
    # Tests disable this - a real socket server per test app instance is
    # unnecessary risk/flakiness when the registry itself is directly
    # inspectable; see tests/integration/test_metrics_endpoint.py.
    metrics_server_enabled: bool = True


class UISettings(BaseModel):
    debug_mode: bool = False
    batch_manual_trigger_visible: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "weather-intelligence-agent"
    env: str = "local"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    http_client: HttpClientSettings = Field(default_factory=HttpClientSettings)
    weather_provider: WeatherProviderSettings = Field(default_factory=WeatherProviderSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    ui: UISettings = Field(default_factory=UISettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
