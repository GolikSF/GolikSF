"""Tool base class and registry.

Every tool declares a name, description, and a pydantic input model. The
registry validates arbitrary dict input against that model before execution,
so a tool implementation never has to deal with malformed input, and the
agent never gets unrestricted access to anything not explicitly registered.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ValidationError


class ToolResult(BaseModel):
    success: bool
    output: Any = None
    error: str | None = None

    def summary(self, max_len: int = 600) -> str:
        text = str(self.output) if self.success else f"ERROR: {self.error}"
        if len(text) > max_len:
            text = text[:max_len] + f"... [truncated, {len(text)} chars total]"
        return text


class Tool(ABC):
    name: str
    description: str
    input_model: type[BaseModel]

    def run(self, tool_input: dict) -> ToolResult:
        try:
            parsed = self.input_model(**(tool_input or {}))
        except ValidationError as exc:
            return ToolResult(success=False, error=f"Invalid input for tool '{self.name}': {exc}")

        try:
            return self._execute(parsed)
        except Exception as exc:  # tools must never crash the agent loop
            return ToolResult(success=False, error=f"Tool '{self.name}' raised an error: {exc}")

    @abstractmethod
    def _execute(self, parsed_input: BaseModel) -> ToolResult: ...

    def input_schema(self) -> dict:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return schema

    def describe(self) -> str:
        return f"- {self.name}: {self.description}\n  input schema: {self.input_schema()}"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def describe_all(self) -> str:
        if not self._tools:
            return "(no tools registered)"
        return "\n".join(tool.describe() for _, tool in sorted(self._tools.items()))
