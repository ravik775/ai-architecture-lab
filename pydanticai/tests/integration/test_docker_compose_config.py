"""Validates docker-compose.yml itself (schema, image refs, profile
wiring) via `docker compose config` - skips gracefully if the Docker CLI
isn't available in the environment running the tests, rather than failing
the whole suite on an unrelated tooling gap.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not available")

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True, scope="module")
def _ensure_env_file():
    """`docker compose config` requires `.env` to exist (same precondition
    as running the stack for real) - create it from `.env.example` if a
    fresh checkout hasn't done that yet. Never overwrites a real `.env`."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        env_path.write_text((REPO_ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")


def _run_compose_config(*extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *extra_args, "config", "--quiet"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_core_compose_config_is_valid():
    result = _run_compose_config()
    assert result.returncode == 0, result.stderr


def test_all_profiles_compose_config_is_valid():
    result = _run_compose_config("--profile", "observability", "--profile", "optional-loki")
    assert result.returncode == 0, result.stderr


def test_all_profiles_include_expected_services():
    result = subprocess.run(
        ["docker", "compose", "--profile", "observability", "--profile", "optional-loki", "config", "--services"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    services = set(result.stdout.split())
    assert {
        "weather-app",
        "litellm-proxy",
        "otel-collector",
        "prometheus",
        "grafana",
        "tempo",
        "loki",
    } <= services


def test_no_service_uses_latest_tag():
    dockerfile_compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert ":latest" not in dockerfile_compose
