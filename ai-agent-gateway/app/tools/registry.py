from app.tools.base import Tool
from app.tools.calculator import SafeCalculatorTool
from app.tools.weather import WeatherTool
from app.tools.web_search import WebSearchTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {
            'calculator': SafeCalculatorTool(),
            'weather': WeatherTool(),
            'web_search': WebSearchTool(),
        }

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
