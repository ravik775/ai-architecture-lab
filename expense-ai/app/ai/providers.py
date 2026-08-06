from threading import Lock

from .models import Provider
from ..config import settings

class ProviderRegistry:
    _providers: list[Provider] = []
    _initialized = False
    _lock = Lock()

    @classmethod
    def _initialize(cls) -> None:
        if cls._initialized:
            return

        with cls._lock:
            if cls._initialized:
                return

            for provider in settings.providers:
                if not provider.enabled:
                    continue

                if not provider.api_key and provider.name != "ollama":
                    raise ValueError(f"Missing API key for provider: {provider.name}")

                if not provider.model:
                    raise ValueError(f"Missing model for provider: {provider.name}")

                cls._providers.append(
                    Provider(
                        name=provider.name,
                        model=provider.model,
                        api_key=provider.api_key,
                        priority=provider.priority,
                        base_url=provider.base_url,
                        enabled=provider.enabled
                    )
                )

            cls._providers.sort(key=lambda p: p.priority)
            cls._initialized = True

    @classmethod
    def providers(cls) -> tuple[Provider, ...]:
        cls._initialize()
        return tuple(cls._providers)

    @classmethod
    def get(cls, name: str) -> Provider:
        cls._initialize()

        for provider in cls._providers:
            if provider.name == name:
                return provider

        raise KeyError(name)