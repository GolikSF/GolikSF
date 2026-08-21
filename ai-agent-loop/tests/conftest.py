"""Shared test fixtures, including a FakeLLMClient that implements the same
`call_structured` interface as the real LLMClient but returns pre-scripted
pydantic model instances -- no network calls, fully deterministic."""

from __future__ import annotations

import pytest

from agent.llm_client import LLMOutputError


class FakeLLMClient:
    """Scripted stand-in for LLMClient. `script` maps tool_name -> a list of
    responses consumed in order (one per call to that tool_name). A response
    may be a pydantic model instance (returned) or an Exception instance
    (raised)."""

    def __init__(self, script: dict[str, list]) -> None:
        self.script = {k: list(v) for k, v in script.items()}
        self.calls: list[dict] = []

    def call_structured(
        self,
        *,
        system: str,
        user_content: str,
        output_model,
        tool_name: str,
        tool_description: str,
        max_tokens: int = 1500,
        max_retries: int = 2,
    ):
        self.calls.append({"tool_name": tool_name, "system": system, "user_content": user_content})
        queue = self.script.get(tool_name)
        if not queue:
            raise LLMOutputError(f"FakeLLMClient: no scripted response left for '{tool_name}'")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_llm_factory():
    return FakeLLMClient


@pytest.fixture
def workspace_dir(tmp_path):
    d = tmp_path / "workspace"
    d.mkdir()
    return d


@pytest.fixture
def runs_dir(tmp_path):
    d = tmp_path / "runs"
    d.mkdir()
    return d
