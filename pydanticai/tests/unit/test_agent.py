"""Agent tests use PydanticAI's `FunctionModel` to script deterministic
tool-calling behavior - no real network/LLM call, per "avoid real external
services in unit tests". This validates OUR wiring (tools -> real services
-> structured output, system-prompt-driven contracts like representative
disclaimers and clarification) - it does not (and cannot, deterministically)
test a real LLM's judgment, which is a live-system concern.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest
from pydantic_ai import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agent.agent import AgentService, build_agent
from app.agent.deps import AgentDeps
from app.application.history_service import HistoryService
from app.application.location_service import LocationService
from app.application.weather_service import WeatherService
from app.config.settings import AgentSettings, CacheSettings, HttpClientSettings
from app.domain.errors import AgentTimeoutError, LocationNotFoundError
from app.domain.models import CollectionType, ProviderName, WeatherObservation
from app.infrastructure.database.models import Base
from app.infrastructure.database.repositories import LocationRepository, ObservationRepository
from app.infrastructure.database.seed import seed
from app.infrastructure.database.session import Database
from app.infrastructure.weather.cache import InMemoryWeatherCache


class _FakeProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def get_current_weather(self, *, location_id: str, **kwargs) -> WeatherObservation:
        if self.fail:
            from app.domain.errors import WeatherProviderUnavailableError

            raise WeatherProviderUnavailableError("upstream down")
        return WeatherObservation(
            location_id=location_id,
            latitude=kwargs["latitude"],
            longitude=kwargs["longitude"],
            observation_time_utc=datetime.now(UTC),
            local_date=date.today(),
            temperature_c=31.0,
            apparent_temperature_c=33.0,
            humidity_percent=55.0,
            precipitation_mm=0.0,
            weather_code=1,
            wind_speed_kmh=10.0,
            wind_direction_deg=200.0,
            provider=ProviderName.OPEN_METEO_FORECAST,
            model="auto",
            unit_system="metric",
            collection_type=CollectionType.ON_DEMAND,
        )

    async def get_daily_weather(self, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError


@pytest.fixture()
async def agent_deps_factory(tmp_path, monkeypatch, request):
    db_path = (tmp_path / "agent.db").as_posix()
    monkeypatch.setenv("DATABASE__URL", f"sqlite+aiosqlite:///{db_path}")

    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    db = Database(settings.database)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed()

    fail = getattr(request, "param", False)
    provider = _FakeProvider(fail=fail)
    location_repository = LocationRepository()
    weather_service = WeatherService(
        provider=provider,
        cache=InMemoryWeatherCache(CacheSettings()),
        db=db,
        location_repository=location_repository,
        cache_settings=CacheSettings(),
        http_settings=HttpClientSettings(),
    )
    location_service = LocationService(db, location_repository)
    history_service = HistoryService(
        db, ObservationRepository(), max_range_days=92, max_page_size=100
    )

    def factory() -> AgentDeps:
        return AgentDeps(
            location_service=location_service, weather_service=weather_service, history_service=history_service
        )

    yield factory
    await db.dispose()
    get_settings.cache_clear()


def _final_result_call(info: AgentInfo, **args) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])


async def test_agent_resolves_representative_location_and_reports_disclaimer(agent_deps_factory):
    step = {"n": 0}

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step["n"] += 1
        if step["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="resolve_supported_location", args={"query": "Hyderabad"})]
            )
        if step["n"] == 2:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="get_current_weather", args={"location_id": "hyderabad"})]
            )
        return _final_result_call(
            info,
            answer="It's 31C and mostly clear in Hyderabad.",
            resolved_location={
                "location_id": "hyderabad",
                "location_name": "Hyderabad",
                "country_name": "India",
                "state_name": "Telangana",
                "is_state_representative": True,
            },
            weather={
                "temperature_c": 31.0,
                "apparent_temperature_c": 33.0,
                "humidity_percent": 55.0,
                "precipitation_mm": 0.0,
                "weather_code": 1,
                "wind_speed_kmh": 10.0,
                "wind_direction_deg": 200.0,
                "observation_time_utc": datetime.now(UTC).isoformat(),
                "provider": "open-meteo-forecast",
                "model": "auto",
            },
            used_representative_location=True,
            representative_disclaimer="Hyderabad is the representative city for Telangana.",
        )

    agent = build_agent(AgentSettings(), model=FunctionModel(script))
    service = AgentService(agent, agent_deps_factory, AgentSettings())

    outcome = await service.query("What's the weather in Hyderabad?")

    assert outcome.result.resolved_location.location_id == "hyderabad"
    assert outcome.result.used_representative_location is True
    assert outcome.result.weather.temperature_c == 31.0
    assert "resolve_supported_location" in outcome.tool_calls
    assert "get_current_weather" in outcome.tool_calls


async def test_agent_asks_for_clarification_on_ambiguous_location(agent_deps_factory):
    step = {"n": 0}

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step["n"] += 1
        if step["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="resolve_supported_location", args={"query": "Springfield"})]
            )
        return _final_result_call(
            info,
            answer="I couldn't find a supported location matching 'Springfield'.",
            needs_clarification=True,
            clarification_options=[],
        )

    agent = build_agent(AgentSettings(), model=FunctionModel(script))
    service = AgentService(agent, agent_deps_factory, AgentSettings())

    outcome = await service.query("Weather in Springfield?")

    assert outcome.result.needs_clarification is True
    assert outcome.result.resolved_location is None


@pytest.mark.parametrize("agent_deps_factory", [True], indirect=True)
async def test_agent_reports_provider_unavailable_without_fabricating(agent_deps_factory):
    step = {"n": 0}

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step["n"] += 1
        if step["n"] == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="get_current_weather", args={"location_id": "hyderabad"})]
            )
        return _final_result_call(
            info,
            answer="Weather for Hyderabad is temporarily unavailable - please try again shortly.",
        )

    agent = build_agent(AgentSettings(), model=FunctionModel(script))
    service = AgentService(agent, agent_deps_factory, AgentSettings())

    outcome = await service.query("Weather in Hyderabad?")

    assert outcome.result.weather is None


async def test_agent_total_latency_budget_enforced(agent_deps_factory):
    async def slow_script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        await asyncio.sleep(0.2)
        return _final_result_call(info, answer="too slow")

    agent = build_agent(AgentSettings(), model=FunctionModel(slow_script))
    service = AgentService(agent, agent_deps_factory, AgentSettings(total_latency_budget_seconds=0.01))

    with pytest.raises(AgentTimeoutError):
        await service.query("anything")


async def test_agent_structured_output_failure_raises_and_is_countable(agent_deps_factory):
    def bad_script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # Missing required "answer" field, every attempt - exhausts retries.
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args={})])

    agent = build_agent(AgentSettings(), model=FunctionModel(bad_script))
    service = AgentService(agent, agent_deps_factory, AgentSettings())

    with pytest.raises(UnexpectedModelBehavior):
        await service.query("anything")
