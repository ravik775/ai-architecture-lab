from typing import Any

from app.ai.models import TokenUsage


def estimate_llm_cost_usd(
    model: str,
    usage: TokenUsage | None,
    model_costs: dict[str, dict[str, Any]] | None,
) -> float | None:
    if not usage or not model_costs:
        return None

    pricing = _find_model_pricing(model, model_costs)
    if not pricing:
        return None

    prompt_tokens = usage.prompt_tokens
    completion_tokens = usage.completion_tokens
    input_cost = pricing.get("input_cost_per_token", 0)
    output_cost = pricing.get("output_cost_per_token", 0)

    return round((prompt_tokens * input_cost) + (completion_tokens * output_cost), 8)


def _find_model_pricing(
    model: str,
    model_costs: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if model in model_costs:
        return model_costs[model]

    normalized_model = model.split("/", 1)[-1]
    return model_costs.get(normalized_model)