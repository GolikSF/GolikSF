"""Thin wrapper around the Anthropic SDK that forces validated, structured
output for every call the agent makes.

Instead of asking the model to write free-form text and hoping to parse it,
every call defines a single-purpose "tool" whose input schema is generated
from a pydantic model, forces the model to call it (tool_choice), and
validates the result. Malformed output is retried a bounded number of times
with the validation error fed back to the model.
"""

from __future__ import annotations

import logging
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMOutputError(RuntimeError):
    """Raised when the model fails to produce valid structured output after retries."""


def _schema_for(model_cls: type[BaseModel]) -> dict:
    schema = model_cls.model_json_schema()
    schema.pop("title", None)
    schema.setdefault("type", "object")
    # Anthropic's tool schema doesn't need $defs cleanup for our flat models,
    # but strip per-property titles for a cleaner prompt surface.
    for prop in schema.get("properties", {}).values():
        prop.pop("title", None)
    return schema


class LLMClient:
    """Real Anthropic-backed client. See FakeLLMClient in tests for the
    interface used during testing (no network calls)."""

    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self.model = model

    def call_structured(
        self,
        *,
        system: str,
        user_content: str,
        output_model: type[T],
        tool_name: str,
        tool_description: str,
        max_tokens: int = 1500,
        max_retries: int = 2,
    ) -> T:
        tool_schema = {
            "name": tool_name,
            "description": tool_description,
            "input_schema": _schema_for(output_model),
        }
        messages: list[dict] = [{"role": "user", "content": user_content}]
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            if last_error is not None:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous call to `{tool_name}` was invalid: {last_error}\n"
                            "Call it again with corrected, schema-valid arguments."
                        ),
                    }
                )

            response = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=[tool_schema],
                tool_choice={"type": "tool", "name": tool_name},
            )

            tool_use = next((block for block in response.content if block.type == "tool_use"), None)
            if tool_use is None:
                last_error = "no tool_use block was returned"
                continue

            try:
                return output_model(**tool_use.input)
            except ValidationError as exc:
                last_error = str(exc)
                logger.debug("Structured output validation failed (attempt %d): %s", attempt, exc)
                continue

        raise LLMOutputError(
            f"Model failed to produce valid `{tool_name}` output after {max_retries + 1} attempts: {last_error}"
        )
