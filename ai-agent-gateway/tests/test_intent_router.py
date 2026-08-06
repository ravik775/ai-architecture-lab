from app.models.schemas import Intent
from app.services.intent_router_o import IntentRouter


def test_weather_intent():
    assert IntentRouter().classify('Weather in Tokyo?') == Intent.weather


def test_math_intent():
    assert IntentRouter().classify('100 + 200') == Intent.calculation
