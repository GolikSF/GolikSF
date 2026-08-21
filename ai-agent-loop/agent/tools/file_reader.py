"""Read-only text file tool, sandboxed to the workspace directory."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from agent.tools.base import Tool, ToolResult
from agent.tools.workspace_paths import UnsafePathError, resolve_within_workspace

MAX_READ_CHARS = 8000


class FileReaderInput(BaseModel):
    path: str = Field(description="Path relative to the workspace directory, e.g. 'notes.txt'.")


class FileReaderTool(Tool):
    name = "read_file"
    description = (
        "Read a text file from the sandboxed workspace directory. "
        "Only files inside the workspace can be read."
    )
    input_model = FileReaderInput

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir

    def _execute(self, parsed_input: FileReaderInput) -> ToolResult:
        try:
            path = resolve_within_workspace(self.workspace_dir, parsed_input.path)
        except UnsafePathError as exc:
            return ToolResult(success=False, error=str(exc))

        if not path.exists():
            return ToolResult(success=False, error=f"File not found in workspace: {parsed_input.path}")
        if not path.is_file():
            return ToolResult(success=False, error=f"Not a file: {parsed_input.path}")

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not read file: {exc}")

        truncated = len(content) > MAX_READ_CHARS
        if truncated:
            content = content[:MAX_READ_CHARS]

        return ToolResult(
            success=True,
            output={
                "path": parsed_input.path,
                "content": content,
                "truncated": truncated,
            },
        )
