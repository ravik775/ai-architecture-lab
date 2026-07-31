from app.observability.cost import estimate_llm_cost_usd
from app.observability.redaction import redact_fields
from app.ai.models import TokenUsage  # Import your TokenUsage model class


def test_redacts_sensitive_fields_but_keeps_token_usage():
    payload = {
        "api_key": "secret",
        "submitted_by": "Ravi",
        "token_usage": {"total_tokens": 100},
        "nested": {"authorization": "Bearer secret"},
    }

    redacted = redact_fields(payload)

    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["submitted_by"] == "[REDACTED]"
    assert redacted["token_usage"] == {"total_tokens": 100}
    assert redacted["nested"]["authorization"] == "[REDACTED]"


def test_estimates_llm_cost_from_model_metadata():
    # Instantiate the TokenUsage object instead of passing a raw dict
    usage = TokenUsage(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )

    model_costs = {
        "test-model": {
            "input_cost_per_token": 0.000001,
            "output_cost_per_token": 0.000002,
        }
    }

    cost = estimate_llm_cost_usd("test-model", usage, model_costs)

    assert cost == 0.0002