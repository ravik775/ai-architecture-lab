import json
import re
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from app.models.schemas import Intent


class RoutingDecision(BaseModel):
    intent: Intent
    city: Optional[str] = None
    math_expression: Optional[str] = None
    search_query: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = "rules"


class IntentRouter:
    WEATHER_WORDS = {
        "weather", "temperature", "forecast", "rain",
        "sunny", "humidity", "wind"
    }

    INTERNET_TRIGGERS = {
        "current", "latest", "today", "news",
        "search", "internet", "recent", "now"
    }

    def __init__(self, llm_client=None, confidence_threshold: float = 0.75):
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold

    async def classify(self, message: str) -> RoutingDecision:
        """
        Hybrid routing:
        1. Use deterministic rules for obvious weather/math/internet requests.
        2. Use LLM router for ambiguous requests.
        3. Fall back to general LLM intent if LLM routing fails.
        """
        rule_decision = self._rule_based_classify(message)

        if rule_decision.confidence >= self.confidence_threshold:
            return rule_decision

        if self.llm_client:
            try:
                llm_decision = await self._llm_classify(message)
                if llm_decision.confidence >= self.confidence_threshold:
                    return llm_decision
            except Exception:
                pass

        return rule_decision

    def _rule_based_classify(self, message: str) -> RoutingDecision:
        text = message.lower().strip()

        if self._looks_like_math(text):
            return RoutingDecision(
                intent=Intent.calculation,
                math_expression=self.extract_math_expression(message),
                confidence=0.98,
                source="rules"
            )

        if any(word in text for word in self.WEATHER_WORDS):
            return RoutingDecision(
                intent=Intent.weather,
                city=self.extract_city(message),
                confidence=0.9,
                source="rules"
            )

        if self._looks_current_or_internet(text):
            return RoutingDecision(
                intent=Intent.internet,
                search_query=message,
                confidence=0.8,
                source="rules"
            )

        return RoutingDecision(
            intent=Intent.llm,
            confidence=0.6,
            source="rules"
        )

    async def _llm_classify(self, message: str) -> RoutingDecision:
        prompt = f"""
You are an intent router for an AI Agent.

Classify the user message into exactly one intent:

weather:
- Weather, temperature, rain, humidity, wind, forecast for a city.

calculation:
- Arithmetic, numeric calculation, math expression.

internet:
- Latest information, current events, news, live facts, public web search.

llm:
- General explanation, reasoning, writing, summarization, coding help.

User message:
{message}

Return only valid JSON with this schema:
{{
  "intent": "weather | calculation | internet | llm",
  "city": "city name or null",
  "math_expression": "expression or null",
  "search_query": "search query or null",
  "confidence": 0.0
}}
"""

        raw_response = await self.llm_client.generate(
            prompt=prompt,
            temperature=0,
            max_tokens=300
        )

        data = self._extract_json(raw_response)

        decision = RoutingDecision(
            intent=Intent(data["intent"]),
            city=data.get("city"),
            math_expression=data.get("math_expression"),
            search_query=data.get("search_query"),
            confidence=data.get("confidence", 0.75),
            source="llm"
        )

        return decision

    def extract_city(self, message: str) -> str:
        patterns = [
            r"\bin\s+([A-Za-z\s]+)\??$",
            r"\bfor\s+([A-Za-z\s]+)\??$",
            r"\bof\s+([A-Za-z\s]+)\??$",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return message.strip()

    def extract_math_expression(self, message: str) -> str:
        normalized = message.replace("^", "**")
        match = re.search(r"([-+*/().\d\s%]+(?:\*\*)?[-+*/().\d\s%]*)", normalized)

        if not match:
            raise ValueError("No arithmetic expression found")

        return match.group(1).strip()

    def _looks_like_math(self, text: str) -> bool:
        return (
            bool(re.search(r"\d+\s*[-+*/%^]\s*\d+", text))
            or text.startswith(("calculate", "compute", "what is"))
            and bool(re.search(r"\d", text))
        )

    def _looks_current_or_internet(self, text: str) -> bool:
        if any(trigger in text for trigger in self.INTERNET_TRIGGERS):
            return True

        if text.startswith(("who is", "what is", "where is")):
            return True

        return False

    def _extract_json(self, raw_response: str) -> dict:
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw_response, re.DOTALL)
            if not match:
                raise ValidationError("LLM response did not contain valid JSON")

            return json.loads(match.group(0))