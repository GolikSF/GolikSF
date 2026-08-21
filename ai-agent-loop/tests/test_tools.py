import pytest

from agent.tools import CalculatorTool, FileReaderTool, FileWriterTool, WebSearchTool
from agent.tools.base import ToolRegistry
from agent.tools.calculator import CalculatorError, safe_eval


def test_calculator_basic_arithmetic():
    tool = CalculatorTool()
    result = tool.run({"expression": "17 * 23.50"})
    assert result.success
    assert result.output["result"] == pytest.approx(399.5)


def test_calculator_handles_tax_style_expression():
    tool = CalculatorTool()
    result = tool.run({"expression": "(17 * 23.50) * 1.0825"})
    assert result.success
    assert result.output["result"] == pytest.approx(432.4587500000001)


def test_calculator_rejects_unsafe_expression():
    with pytest.raises(CalculatorError):
        safe_eval("__import__('os').system('echo hi')")


def test_calculator_rejects_bad_syntax():
    tool = CalculatorTool()
    result = tool.run({"expression": "17 *"})
    assert not result.success
    assert result.error


def test_calculator_division_by_zero():
    tool = CalculatorTool()
    result = tool.run({"expression": "1 / 0"})
    assert not result.success
    assert "zero" in result.error.lower()


def test_calculator_invalid_input_schema():
    tool = CalculatorTool()
    result = tool.run({})  # missing required field
    assert not result.success
    assert "Invalid input" in result.error


def test_file_writer_and_reader_roundtrip(workspace_dir):
    writer = FileWriterTool(workspace_dir)
    reader = FileReaderTool(workspace_dir)

    write_result = writer.run({"filename": "out.txt", "content": "hello world"})
    assert write_result.success

    read_result = reader.run({"path": "out.txt"})
    assert read_result.success
    assert read_result.output["content"] == "hello world"


def test_file_reader_missing_file(workspace_dir):
    reader = FileReaderTool(workspace_dir)
    result = reader.run({"path": "does_not_exist.txt"})
    assert not result.success
    assert "not found" in result.error.lower()


def test_file_writer_rejects_path_traversal(workspace_dir):
    writer = FileWriterTool(workspace_dir)
    result = writer.run({"filename": "../escape.txt", "content": "x"})
    assert not result.success  # filename validator rejects '/' before path check even runs


def test_file_reader_rejects_path_traversal(workspace_dir):
    reader = FileReaderTool(workspace_dir)
    result = reader.run({"path": "../../etc/passwd"})
    assert not result.success
    assert "outside" in result.error.lower()


def test_file_writer_rejects_oversized_content(workspace_dir):
    writer = FileWriterTool(workspace_dir)
    result = writer.run({"filename": "big.txt", "content": "x" * 999999})
    assert not result.success
    assert "too large" in result.error.lower()


def test_web_search_disabled_without_key():
    tool = WebSearchTool(search_api_key=None)
    result = tool.run({"query": "anything"})
    assert not result.success
    assert "not configured" in result.error.lower()


def test_tool_registry_register_and_describe():
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    assert registry.names() == ["calculator"]
    assert registry.get("calculator") is not None
    assert registry.get("nonexistent") is None
    assert "calculator" in registry.describe_all()


def test_tool_execution_error_is_caught_not_raised():
    class BrokenTool(CalculatorTool):
        def _execute(self, parsed_input):
            raise RuntimeError("boom")

    tool = BrokenTool()
    result = tool.run({"expression": "1+1"})
    assert not result.success
    assert "boom" in result.error
