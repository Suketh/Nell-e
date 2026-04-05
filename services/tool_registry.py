from dataclasses import dataclass
from typing import Any, Callable

from services.tools.browser_control import open_in_browser
from services.tools.calculator_safe import evaluate_expression
from services.tools.datetime_local import lookup_local_datetime
from services.tools.weather_open_meteo import lookup_weather
from services.tools.web_fetch import fetch_webpage
from services.tools.wikipedia_search import search_wikipedia


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., Any]


class ToolRegistry:
    def __init__(self, ollama=None):
        self.ollama = ollama
        self._tools: dict[str, ToolSpec] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(
            ToolSpec(
                name="datetime_local",
                description="Look up the current local time, date, weekday, month, year, and ISO week.",
                input_schema={},
                handler=lambda: lookup_local_datetime(),
            )
        )
        self.register(
            ToolSpec(
                name="calculator",
                description="Evaluate a simple arithmetic expression safely.",
                input_schema={"expression": "str"},
                handler=lambda expression: evaluate_expression(expression),
            )
        )
        self.register(
            ToolSpec(
                name="weather_lookup",
                description="Look up the current weather for a city or place name.",
                input_schema={"location": "str"},
                handler=lambda location: lookup_weather(location),
            )
        )
        self.register(
            ToolSpec(
                name="web_search",
                description="Search the web for lightweight lookup tasks.",
                input_schema={"q": "str", "k": "int"},
                handler=self._web_search,
            )
        )
        self.register(
            ToolSpec(
                name="web_fetch",
                description="Fetch a webpage URL and extract its title and visible text.",
                input_schema={"url": "str", "max_chars": "int"},
                handler=lambda url, max_chars=4000: fetch_webpage(url=url, max_chars=max_chars),
            )
        )
        self.register(
            ToolSpec(
                name="wikipedia_search",
                description="Search Wikipedia and return short summaries with article links.",
                input_schema={"query": "str", "limit": "int"},
                handler=lambda query, limit=3: search_wikipedia(query=query, limit=limit),
            )
        )
        self.register(
            ToolSpec(
                name="browser_open",
                description="Open Chrome for Spotify, YouTube, Wikipedia, or a provided URL/search query.",
                input_schema={"target": "str", "url": "str", "query": "str"},
                handler=lambda target=None, url=None, query=None: open_in_browser(target=target, url=url, query=query),
            )
        )
        self.register(
            ToolSpec(
                name="pdf_extract_text",
                description="Extract text from a PDF path.",
                input_schema={"pdf_path": "str", "max_pages": "int"},
                handler=self._pdf_extract_text,
            )
        )
        self.register(
            ToolSpec(
                name="vision_describe_image",
                description="Describe a local image with the current vision model.",
                input_schema={"image_path": "str"},
                handler=self._vision_describe_image,
            )
        )

    def register(self, spec: ToolSpec):
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def _web_search(self, q: str, k: int = 5):
        from services.tools.web_duckduckgo import search

        return search(q=q, k=k)

    def _pdf_extract_text(self, pdf_path: str, max_pages: int = 30):
        from services.tools.pdf_pymupdf import extract_text

        return extract_text(pdf_path=pdf_path, max_pages=max_pages)

    def _vision_describe_image(self, image_path: str):
        from services.tools.vision_ollama import describe_image

        return describe_image(self.ollama, image_path)
