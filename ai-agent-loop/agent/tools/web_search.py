"""Web search tool.

Designed so the architecture supports web search cleanly, but it is disabled
by default and never fabricates results: if no SEARCH_API_KEY is configured
it returns a clear, structured failure instead of pretending to search.

When SEARCH_API_KEY is set, it queries the Brave Search API
(https://api.search.brave.com) and returns real results.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent.tools.base import Tool, ToolResult

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class WebSearchInput(BaseModel):
    query: str = Field(description="Search query.")
    max_results: int = Field(default=5, ge=1, le=10)


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web for current information. DISABLED unless SEARCH_API_KEY is configured "
        "in the environment; will return an error explaining that if used while disabled."
    )
    input_model = WebSearchInput

    def __init__(self, search_api_key: str | None) -> None:
        self.search_api_key = search_api_key

    def _execute(self, parsed_input: WebSearchInput) -> ToolResult:
        if not self.search_api_key:
            return ToolResult(
                success=False,
                error=(
                    "Web search is not configured. Set SEARCH_API_KEY (a Brave Search API key) "
                    "in .env to enable this tool. No results were fabricated."
                ),
            )

        import requests

        try:
            response = requests.get(
                BRAVE_SEARCH_URL,
                params={"q": parsed_input.query, "count": parsed_input.max_results},
                headers={"X-Subscription-Token": self.search_api_key, "Accept": "application/json"},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return ToolResult(success=False, error=f"Web search request failed: {exc}")

        data = response.json()
        results = [
            {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description")}
            for r in data.get("web", {}).get("results", [])[: parsed_input.max_results]
        ]
        if not results:
            return ToolResult(success=True, output={"query": parsed_input.query, "results": []})
        return ToolResult(success=True, output={"query": parsed_input.query, "results": results})
