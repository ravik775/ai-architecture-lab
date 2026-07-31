import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic_settings import (
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


# app.config creates its module-level settings object during import.
# Force basic mode while importing so Postgres is not required.
_original_agentic_expense = os.environ.get(
    "AGENTIC_EXPENSE"
)
os.environ["AGENTIC_EXPENSE"] = "false"

from app.config import Settings  # noqa: E402

if _original_agentic_expense is None:
    os.environ.pop("AGENTIC_EXPENSE", None)
else:
    os.environ["AGENTIC_EXPENSE"] = (
        _original_agentic_expense
    )


DEFAULT_VALUE = 50
SECRET_VALUE = 40
YAML_VALUE = 30
DOTENV_VALUE = 20
ENV_VALUE = 10
INIT_VALUE = 5


MANAGED_ENVIRONMENT_VARIABLES = {
    "PRECEDENCE_PROBE",
    "AGENTIC_EXPENSE",
    "CONFIG_DEBUG",

    "DATA__DATABASE_URL",
    "DATA__DATABASE_SSLMODE",
    # Unsupported flat database names are cleared so a developer's
    # machine or CI environment cannot affect these tests.
    "DATABASE_URL",
    "DATABASE_SSLMODE",

    "RUNTIME__TIMEOUT_SECONDS",
    "RUNTIME__MAX_RETRIES",
    "RUNTIME_TIMEOUT_SECONDS",
    "RUNTIME_MAX_RETRIES",

    "RAG__PERSIST_DIRECTORY",
    "RAG_PERSIST_DIRECTORY",

    "OBSERVABILITY__TRACING_ENABLED",
    "OBSERVABILITY__METRICS_ENABLED",
    "OBSERVABILITY__CONSOLE_TRACE_EXPORTER_ENABLED",
    "OBSERVABILITY__CONSOLE_METRIC_EXPORTER_ENABLED",
    "OTEL_CONSOLE_TRACE_ENABLED",
}


@pytest.fixture(autouse=True)
def clear_managed_environment(monkeypatch):
    """
    Prevent the project environment and .env values from leaking
    into isolated configuration tests.
    """
    for variable_name in (
        MANAGED_ENVIRONMENT_VARIABLES
    ):
        monkeypatch.delenv(
            variable_name,
            raising=False,
        )


def create_test_settings(
    tmp_path: Path,
    *,
    yaml_value: int | None = None,
    dotenv_value: int | None = None,
    secret_value: int | None = None,
) -> type[Settings]:
    """
    Create an isolated Settings subclass with temporary YAML,
    dotenv and secret sources.
    """
    yaml_file = tmp_path / "application.yaml"
    env_file = tmp_path / ".env"
    secrets_dir = tmp_path / "secrets"

    secrets_dir.mkdir(exist_ok=True)

    yaml_content = [
        "data:",
        "  database_url: null",
        "  database_sslmode: prefer",
    ]

    if yaml_value is not None:
        yaml_content.append(
            f"precedence_probe: {yaml_value}"
        )

    yaml_file.write_text(
        "\n".join(yaml_content) + "\n",
        encoding="utf-8",
    )

    if dotenv_value is None:
        env_file.write_text(
            "",
            encoding="utf-8",
        )
    else:
        env_file.write_text(
            f"PRECEDENCE_PROBE={dotenv_value}\n",
            encoding="utf-8",
        )

    if secret_value is not None:
        (
            secrets_dir / "precedence_probe"
        ).write_text(
            str(secret_value),
            encoding="utf-8",
        )

    class TestSettings(Settings):
        precedence_probe: int = DEFAULT_VALUE
        agentic_expense: bool = False

        model_config = SettingsConfigDict(
            yaml_file=yaml_file,
            env_file=env_file,
            env_file_encoding="utf-8",
            env_nested_delimiter="__",
            secrets_dir=secrets_dir,
            case_sensitive=False,
            extra="ignore",
            hide_input_in_errors=True,
        )

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type["TestSettings"],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            return (
                init_settings,
                env_settings,
                dotenv_settings,
                YamlConfigSettingsSource(
                    settings_cls
                ),
                file_secret_settings,
            )

    return TestSettings


# ------------------------------------------------------------------
# Settings source precedence
# ------------------------------------------------------------------


def test_model_default_used_when_no_source_exists(
    tmp_path,
):
    settings_class = create_test_settings(tmp_path)
    result = settings_class()

    assert result.precedence_probe == DEFAULT_VALUE


def test_secret_overrides_model_default(
    tmp_path,
):
    settings_class = create_test_settings(
        tmp_path,
        secret_value=SECRET_VALUE,
    )
    result = settings_class()

    assert result.precedence_probe == SECRET_VALUE


def test_yaml_overrides_secret(
    tmp_path,
):
    settings_class = create_test_settings(
        tmp_path,
        yaml_value=YAML_VALUE,
        secret_value=SECRET_VALUE,
    )
    result = settings_class()

    assert result.precedence_probe == YAML_VALUE


def test_dotenv_overrides_yaml_and_secret(
    tmp_path,
):
    settings_class = create_test_settings(
        tmp_path,
        yaml_value=YAML_VALUE,
        dotenv_value=DOTENV_VALUE,
        secret_value=SECRET_VALUE,
    )
    result = settings_class()

    assert result.precedence_probe == DOTENV_VALUE


def test_environment_overrides_dotenv_yaml_and_secret(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "PRECEDENCE_PROBE",
        str(ENV_VALUE),
    )

    settings_class = create_test_settings(
        tmp_path,
        yaml_value=YAML_VALUE,
        dotenv_value=DOTENV_VALUE,
        secret_value=SECRET_VALUE,
    )
    result = settings_class()

    assert result.precedence_probe == ENV_VALUE


def test_initializer_overrides_all_other_sources(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "PRECEDENCE_PROBE",
        str(ENV_VALUE),
    )

    settings_class = create_test_settings(
        tmp_path,
        yaml_value=YAML_VALUE,
        dotenv_value=DOTENV_VALUE,
        secret_value=SECRET_VALUE,
    )

    result = settings_class(
        precedence_probe=INIT_VALUE,
    )

    assert result.precedence_probe == INIT_VALUE


# ------------------------------------------------------------------
# Nested environment variables
# ------------------------------------------------------------------


def test_nested_runtime_environment_variables(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "RUNTIME__TIMEOUT_SECONDS",
        "17",
    )
    monkeypatch.setenv(
        "RUNTIME__MAX_RETRIES",
        "1",
    )

    settings_class = create_test_settings(tmp_path)
    result = settings_class()

    assert result.runtime.timeout_seconds == 17
    assert result.runtime.max_retries == 1


def test_nested_database_environment_variables(
    tmp_path,
    monkeypatch,
):
    database_url = (
        "postgresql://local-user:local-pass"
        "@localhost:5432/expense"
    )

    monkeypatch.setenv(
        "DATA__DATABASE_URL",
        database_url,
    )
    monkeypatch.setenv(
        "DATA__DATABASE_SSLMODE",
        "disable",
    )

    settings_class = create_test_settings(tmp_path)
    result = settings_class(
        agentic_expense=True,
    )

    assert (
        result.data.database_url
        == database_url
    )
    assert (
        result.data.database_sslmode
        == "disable"
    )


def test_nested_rag_and_observability_variables(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "RAG__PERSIST_DIRECTORY",
        "/tmp/chroma-test",
    )
    monkeypatch.setenv(
        "OBSERVABILITY__TRACING_ENABLED",
        "true",
    )
    monkeypatch.setenv(
        "OBSERVABILITY__METRICS_ENABLED",
        "false",
    )
    monkeypatch.setenv(
        "OBSERVABILITY__CONSOLE_TRACE_EXPORTER_ENABLED",
        "true",
    )

    settings_class = create_test_settings(tmp_path)
    result = settings_class()

    assert (
        result.rag.persist_directory
        == "/tmp/chroma-test"
    )
    assert (
        result.observability.tracing_enabled
        is True
    )
    assert (
        result.observability.metrics_enabled
        is False
    )
    assert (
        result.observability
        .console_trace_exporter_enabled
        is True
    )


# ------------------------------------------------------------------
# Unsupported flat database variables
# ------------------------------------------------------------------


def test_flat_database_variables_do_not_override_nested_values(
    tmp_path,
    monkeypatch,
):
    nested_url = (
        "postgresql://local-user:local-pass"
        "@localhost:5432/expense"
    )
    flat_url = (
        "postgresql://platform-user:platform-pass"
        "@database.example.com:5432/expense"
    )

    monkeypatch.setenv(
        "DATA__DATABASE_URL",
        nested_url,
    )
    monkeypatch.setenv(
        "DATA__DATABASE_SSLMODE",
        "disable",
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        flat_url,
    )
    monkeypatch.setenv(
        "DATABASE_SSLMODE",
        "require",
    )

    settings_class = create_test_settings(tmp_path)
    result = settings_class(
        agentic_expense=True,
    )

    assert result.data.database_url == nested_url
    assert result.data.database_sslmode == "disable"


# ------------------------------------------------------------------
# Supported flat non-database compatibility variables
# ------------------------------------------------------------------


def test_supported_flat_non_database_variables(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "RUNTIME_TIMEOUT_SECONDS",
        "10",
    )
    monkeypatch.setenv(
        "RUNTIME_MAX_RETRIES",
        "1",
    )
    monkeypatch.setenv(
        "RAG_PERSIST_DIRECTORY",
        "/tmp/chroma",
    )
    monkeypatch.setenv(
        "OTEL_CONSOLE_TRACE_ENABLED",
        "true",
    )

    settings_class = create_test_settings(tmp_path)
    result = settings_class()

    assert result.data.database_sslmode == "prefer"
    assert result.runtime.timeout_seconds == 10
    assert result.runtime.max_retries == 1
    assert (
        result.rag.persist_directory
        == "/tmp/chroma"
    )
    assert (
        result.observability
        .console_trace_exporter_enabled
        is True
    )


# ------------------------------------------------------------------
# Basic and agentic modes
# ------------------------------------------------------------------


def test_basic_mode_does_not_require_database_url(
    tmp_path,
):
    settings_class = create_test_settings(tmp_path)

    result = settings_class(
        agentic_expense=False,
    )

    assert result.agentic_expense is False
    assert result.data.database_url is None


def test_agentic_mode_requires_database_url(
    tmp_path,
):
    settings_class = create_test_settings(tmp_path)

    with pytest.raises(
        ValueError,
        match="Postgres is required",
    ):
        settings_class(
            agentic_expense=True,
        )


# ------------------------------------------------------------------
# Lazy Postgres initialization
# ------------------------------------------------------------------


def test_importing_expense_graph_does_not_create_pool():
    module_name = (
        "app.agents.expense_approval_graph"
    )

    sys.modules.pop(module_name, None)

    with patch(
        "psycopg_pool.ConnectionPool",
    ) as connection_pool_class:
        importlib.import_module(module_name)
        connection_pool_class.assert_not_called()

    sys.modules.pop(module_name, None)


def test_checkpointer_resources_created_once_and_cached(
    monkeypatch,
):
    module = importlib.import_module(
        "app.agents.expense_approval_graph"
    )

    database_url = (
        "postgresql://test-user:test-pass"
        "@database.example.com:5432/expense"
    )

    monkeypatch.setattr(
        module.settings.data,
        "database_url",
        database_url,
    )
    monkeypatch.setattr(
        module.settings.data,
        "database_sslmode",
        "require",
    )

    fake_connection = MagicMock()
    fake_pool = MagicMock()

    fake_pool.connection.return_value.__enter__.return_value = (
        fake_connection
    )

    setup_saver = MagicMock()
    runtime_saver = MagicMock()

    connection_pool_factory = MagicMock(
        return_value=fake_pool,
    )
    postgres_saver_factory = MagicMock(
        side_effect=[
            setup_saver,
            runtime_saver,
        ],
    )

    monkeypatch.setattr(
        module,
        "ConnectionPool",
        connection_pool_factory,
    )
    monkeypatch.setattr(
        module,
        "PostgresSaver",
        postgres_saver_factory,
    )

    module.get_checkpointer_resources.cache_clear()

    try:
        first_result = (
            module.get_checkpointer_resources()
        )
        second_result = (
            module.get_checkpointer_resources()
        )

        assert first_result is second_result
        connection_pool_factory.assert_called_once()
        assert (
            postgres_saver_factory.call_count
            == 2
        )

        postgres_saver_factory.assert_any_call(
            fake_connection
        )
        postgres_saver_factory.assert_any_call(
            fake_pool
        )

        setup_saver.setup.assert_called_once()

        assert first_result == (
            fake_pool,
            runtime_saver,
        )
    finally:
        module.get_checkpointer_resources.cache_clear()