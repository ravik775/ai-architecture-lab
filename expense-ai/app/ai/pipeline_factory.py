import importlib
from functools import lru_cache

from app.ai.pipeline import Pipeline
from app.ai.policies.base import Policy
from app.config import settings


class PipelineFactory:

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_policies() -> list[Policy]:
        for policy_name in settings.pipeline.policies:
            importlib.import_module(f"app.ai.policies.{policy_name}_policy")

        policies = sorted(
            (Policy.registry[name]() for name in settings.pipeline.policies),
            key=lambda p: p.priority
        )
        policy_names = [p.name for p in policies]
        print("Loaded policies:"+("\n\t".join(policy_names)))
        return policies

    @classmethod
    def build(cls) -> Pipeline:
        return Pipeline(cls._get_policies())