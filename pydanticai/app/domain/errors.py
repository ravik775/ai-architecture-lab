"""Shared error types raised by infrastructure, caught by application/agent."""
from __future__ import annotations


class WeatherProviderError(Exception):
    """Base class for any failure retrieving weather from an upstream provider."""


class WeatherProviderTimeoutError(WeatherProviderError):
    """The provider did not respond within the configured latency budget."""


class WeatherProviderUnavailableError(WeatherProviderError):
    """The provider returned a transient error after exhausting retries."""


class InvalidCoordinatesError(ValueError):
    pass


class InvalidTimezoneError(ValueError):
    pass


class LocationNotFoundError(Exception):
    pass


class AmbiguousLocationError(Exception):
    def __init__(self, candidates: list[str]) -> None:
        self.candidates = candidates
        super().__init__(f"Ambiguous location, candidates: {candidates}")


class BatchAlreadyRunningError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"A daily collection run is already in progress: {job_id}")


class AgentTimeoutError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    def __init__(self, username: str) -> None:
        self.username = username
        super().__init__(f"Username already exists: {username}")


class InvalidCredentialsError(Exception):
    pass
