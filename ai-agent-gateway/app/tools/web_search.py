from typing import Any
from ddgs import DDGS

from app.tools.base import Tool


class WebSearchTool(Tool):
    name = 'web_search'
    description = 'Searches the internet for general current-information questions.'

    def run(self, query: str, max_results: int = 5, **_: Any) -> dict[str, Any]:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        simplified = [
            {
                'title': item.get('title'),
                'href': item.get('href'),
                'body': item.get('body'),
            }
            for item in results
        ]
        return {'query': query, 'results': simplified}
