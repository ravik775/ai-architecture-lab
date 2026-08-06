import importlib
from functools import lru_cache
import logging

from app.ai.pipeline import Pipeline
from app.ai.policies.base import Policy
from app.config import settings

logger = logging.getLogger(__name__)


class PipelineFactory:

    @staticmethod
    def _load_modules() -> None:
        """Dynamically loads all policy modules defined in settings."""
        for policy_name in settings.pipeline.policies:
            try:
                importlib.import_module(f"app.ai.policies.{policy_name}_policy")
            except Exception as e:
                logger.error(f"Failed to import policy module: {policy_name}_policy", exc_info=True)

    @staticmethod
    def _validate(configured_policies: list[str]) -> list[str]:
        """Validates that all configured policies were successfully registered.

        Prints all missing policies at the end of validation.
        """
        registered_names = Policy.registry.keys()
        missing_policies = [name for name in configured_policies if name not in registered_names]

        if missing_policies:
            for policy in missing_policies:
                logger.error(
                    f"Missing policy detected: Policy '{policy}' was configured but failed to load or register.")
            raise ValueError(f"Pipeline validation failed. Missing policies: {missing_policies}")

        return missing_policies

    @staticmethod
    def _create_policies(policy_names: list[str]) -> list[Policy]:
        """Instantiates and sorts policies based on priority."""
        policies = sorted(
            (Policy.registry[name]() for name in policy_names),
            key=lambda p: p.priority
        )
        return policies

    @classmethod
    @lru_cache(maxsize=1)
    def _get_policies(cls) -> list[Policy]:
        configured_policies = settings.pipeline.policies

        cls._load_modules()
        cls._validate(configured_policies)
        policies = cls._create_policies(configured_policies)

        policy_names = [p.name for p in policies]
        logger.info("Pipeline initialized with policies: %s", policy_names)
        return policies

    @classmethod
    def build(cls) -> Pipeline:
        return Pipeline(cls._get_policies())