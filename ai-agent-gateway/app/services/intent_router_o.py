import re
from app.models.schemas import Intent


class IntentRouter:
    WEATHER_WORDS = {'weather', 'temperature', 'forecast', 'rain', 'sunny', 'humidity', 'wind'}

    def classify(self, message: str) -> Intent:
        text = message.lower()
        if any(word in text for word in self.WEATHER_WORDS):
            return Intent.weather
        if self._looks_like_math(text):
            return Intent.calculation
        if self._looks_current_or_internet(text):
            return Intent.internet
        return Intent.llm

    def extract_city(self, message: str) -> str:
        patterns = [r'in\s+([A-Za-z\s]+)\??$', r'for\s+([A-Za-z\s]+)\??$']
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return message.strip()

    def extract_math_expression(self, message: str) -> str:
        match = re.search(r'([-+*/().\d\s%^]+)', message.replace('^', '**'))
        if not match:
            raise ValueError('No arithmetic expression found')
        return match.group(1).strip()

    def _looks_like_math(self, text: str) -> bool:
        return bool(re.search(r'\d+\s*[-+*/%^]\s*\d+', text)) or text.startswith(('calculate', 'compute'))

    def _looks_current_or_internet(self, text: str) -> bool:
        triggers = ('current', 'latest', 'today', 'news', 'who is', 'what is', 'search', 'internet')
        return any(trigger in text for trigger in triggers)
