"""
Structural sanity checks on the YAML/compose files - not a substitute
for `docker compose up` (nothing here starts a real Collector), but
enough to catch a broken reference or a typo'd processor/exporter name
before it reaches a real deployment. Paths are resolved relative to the
repo root so this suite can run from any working directory.
"""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(relative_path: str) -> dict:
    return yaml.safe_load((REPO_ROOT / relative_path).read_text())


# ------------------------------------------------------- base collector --
def test_base_collector_config_has_tail_sampling_with_both_policies():
    cfg = _load("collector/otel-collector-config.yaml")
    tail_sampling = cfg["processors"]["tail_sampling"]
    policy_names = {p["name"] for p in tail_sampling["policies"]}
    assert policy_names == {"always-keep-errors", "rate-limit-the-rest"}

    error_policy = next(p for p in tail_sampling["policies"] if p["name"] == "always-keep-errors")
    assert error_policy["type"] == "status_code"
    assert "ERROR" in error_policy["status_code"]["status_codes"]

    rate_policy = next(p for p in tail_sampling["policies"] if p["name"] == "rate-limit-the-rest")
    assert rate_policy["type"] == "rate_limiting"
    assert rate_policy["rate_limiting"]["spans_per_second"] > 0


def test_base_collector_traces_pipeline_runs_tail_sampling_before_batch():
    cfg = _load("collector/otel-collector-config.yaml")
    processors = cfg["service"]["pipelines"]["traces"]["processors"]
    assert processors.index("tail_sampling") < processors.index("batch")


# --------------------------------------------------- Layer 2: redaction --
def test_base_collector_redaction_processor_is_allowlist_mode():
    cfg = _load("collector/otel-collector-config.yaml")
    redaction = cfg["processors"]["redaction"]
    assert redaction["allow_all_keys"] is False
    assert len(redaction["allowed_keys"]) > 0
    assert len(redaction["blocked_values"]) == 6  # email/phone/CC/SSN/API-key/IPv4


def test_base_collector_redaction_allowlist_excludes_pii_risk_keys():
    cfg = _load("collector/otel-collector-config.yaml")
    allowed = set(cfg["processors"]["redaction"]["allowed_keys"])
    # http.target/http.url carry the resolved request path (may embed a
    # user-supplied session_id); net.peer.ip/client.address is the
    # caller's IP. Both deliberately excluded - see the YAML comments.
    for risky_key in ("http.target", "http.url", "net.peer.ip", "client.address"):
        assert risky_key not in allowed


def test_base_collector_redaction_allowlist_covers_known_app_attributes():
    cfg = _load("collector/otel-collector-config.yaml")
    allowed = set(cfg["processors"]["redaction"]["allowed_keys"])
    # Spot-check a representative attribute from each span-producing
    # module (app/api/routes.py, app/llm/chain.py, app/health/monitor.py,
    # app/observability/tracing.py) so a future rename gets caught here
    # instead of silently dropping telemetry in production.
    for key in (
        "app.session_id",
        "app.llm.cost_usd",
        "app.health.success_rate",
        "gen_ai.request.model",
        "http.route",
    ):
        assert key in allowed


def test_base_collector_traces_pipeline_runs_redaction_after_tail_sampling_before_batch():
    cfg = _load("collector/otel-collector-config.yaml")
    processors = cfg["service"]["pipelines"]["traces"]["processors"]
    assert processors.index("tail_sampling") < processors.index("redaction") < processors.index("batch")


def test_tls_collector_redaction_processor_matches_base():
    base = _load("collector/otel-collector-config.yaml")["processors"]["redaction"]
    tls = _load("collector/otel-collector-config.tls.yaml")["processors"]["redaction"]
    assert base == tls


def test_base_collector_metrics_pipeline_exports_to_prometheus():
    cfg = _load("collector/otel-collector-config.yaml")
    assert "prometheus" in cfg["service"]["pipelines"]["metrics"]["exporters"]
    assert "prometheus" in cfg["exporters"]


def test_base_collector_receiver_is_plaintext_no_tls_block():
    cfg = _load("collector/otel-collector-config.yaml")
    http_receiver = cfg["receivers"]["otlp"]["protocols"]["http"]
    assert "tls" not in http_receiver


# -------------------------------------------------------- TLS collector --
def test_tls_collector_receiver_requires_client_cert():
    cfg = _load("collector/otel-collector-config.tls.yaml")
    http_receiver = cfg["receivers"]["otlp"]["protocols"]["http"]
    tls = http_receiver["tls"]
    assert tls["cert_file"]
    assert tls["key_file"]
    assert tls["client_ca_file"]  # presence = mTLS (require + verify client cert)


def test_tls_collector_prometheus_exporter_has_tls():
    cfg = _load("collector/otel-collector-config.tls.yaml")
    prom = cfg["exporters"]["prometheus"]
    assert prom["tls"]["cert_file"]
    assert prom["tls"]["key_file"]


def test_tls_collector_keeps_same_pipeline_shape_as_base():
    base = _load("collector/otel-collector-config.yaml")["service"]["pipelines"]
    tls = _load("collector/otel-collector-config.tls.yaml")["service"]["pipelines"]
    # Same receivers/processors/exporters wiring - only the transport
    # security changed, not the observability pipeline itself.
    assert base["traces"]["exporters"] == tls["traces"]["exporters"]
    assert base["metrics"]["exporters"] == tls["metrics"]["exporters"]


# ------------------------------------------------------------ prometheus --
def test_prometheus_tls_scrape_config_uses_https():
    cfg = _load("collector/prometheus.tls.yml")
    job = cfg["scrape_configs"][0]
    assert job["scheme"] == "https"
    assert job["tls_config"]["ca_file"]


def test_prometheus_plaintext_scrape_config_has_no_scheme_override():
    cfg = _load("collector/prometheus.yml")
    job = cfg["scrape_configs"][0]
    assert job.get("scheme", "http") != "https"


# ---------------------------------------------------------------- compose --
def test_docker_compose_has_expected_services():
    cfg = _load("docker-compose.yml")
    assert set(cfg["services"].keys()) == {"otel-collector", "prometheus", "app"}


def test_docker_compose_tls_overlay_only_touches_existing_services():
    base = _load("docker-compose.yml")
    overlay = _load("docker-compose.tls.yml")
    assert set(overlay["services"].keys()) <= set(base["services"].keys())


def test_docker_compose_tls_overlay_sets_https_endpoint():
    overlay = _load("docker-compose.tls.yml")
    app_env = overlay["services"]["app"]["environment"]
    assert app_env["OTEL_EXPORTER_OTLP_ENDPOINT"].startswith("https://")
    assert app_env["OTEL_TLS_ENABLED"] == "true"
