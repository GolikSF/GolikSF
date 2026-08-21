"""Tests for LLMClient's structured-output + retry-on-malformed-output logic.
The real Anthropic SDK client is mocked out entirely -- no network calls."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

from agent.llm_client import LLMClient, LLMOutputError


class DummyOutput(BaseModel):
    value: int


def _tool_use_response(tool_input: dict):
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=tool_input, name="test_tool")])


def _no_tool_use_response():
    return SimpleNamespace(content=[SimpleNamespace(type="text", text="I didn't call the tool")])


@patch("agent.llm_client.anthropic.Anthropic")
def test_call_structured_success_first_try(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _tool_use_response({"value": 7})

    llm = LLMClient(api_key="k", model="m")
    result = llm.call_structured(
        system="sys",
        user_content="hi",
        output_model=DummyOutput,
        tool_name="test_tool",
        tool_description="desc",
    )

    assert result.value == 7
    assert mock_client.messages.create.call_count == 1


@patch("agent.llm_client.anthropic.Anthropic")
def test_call_structured_recovers_from_malformed_output(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _tool_use_response({}),  # missing required field -> ValidationError
        _tool_use_response({"value": 9}),  # valid on retry
    ]

    llm = LLMClient(api_key="k", model="m")
    result = llm.call_structured(
        system="sys",
        user_content="hi",
        output_model=DummyOutput,
        tool_name="test_tool",
        tool_description="desc",
        max_retries=2,
    )

    assert result.value == 9
    assert mock_client.messages.create.call_count == 2


@patch("agent.llm_client.anthropic.Anthropic")
def test_call_structured_recovers_from_missing_tool_use(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.side_effect = [
        _no_tool_use_response(),
        _tool_use_response({"value": 3}),
    ]

    llm = LLMClient(api_key="k", model="m")
    result = llm.call_structured(
        system="sys", user_content="hi", output_model=DummyOutput, tool_name="test_tool", tool_description="d"
    )
    assert result.value == 3


@patch("agent.llm_client.anthropic.Anthropic")
def test_call_structured_raises_after_exhausting_retries(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client
    mock_client.messages.create.return_value = _tool_use_response({})  # always invalid

    llm = LLMClient(api_key="k", model="m")
    try:
        llm.call_structured(
            system="sys",
            user_content="hi",
            output_model=DummyOutput,
            tool_name="test_tool",
            tool_description="d",
            max_retries=1,
        )
        assert False, "expected LLMOutputError"
    except LLMOutputError:
        pass

    assert mock_client.messages.create.call_count == 2  # 1 initial + 1 retry
