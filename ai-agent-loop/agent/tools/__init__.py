from agent.tools.base import Tool, ToolRegistry, ToolResult
from agent.tools.calculator import CalculatorTool
from agent.tools.file_reader import FileReaderTool
from agent.tools.file_writer import FileWriterTool
from agent.tools.web_search import WebSearchTool

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "CalculatorTool",
    "FileReaderTool",
    "FileWriterTool",
    "WebSearchTool",
    "build_default_registry",
]


def build_default_registry(workspace_dir, search_api_key=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(FileReaderTool(workspace_dir))
    registry.register(FileWriterTool(workspace_dir))
    registry.register(WebSearchTool(search_api_key))
    return registry
