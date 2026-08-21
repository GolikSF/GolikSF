"""File-writing tool, sandboxed to the workspace directory.

Filenames are restricted to a safe character set and cannot contain path
separators, so a model can never write outside the sandbox regardless of
what it puts in `filename`.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from agent.tools.base import Tool, ToolResult
from agent.tools.workspace_paths import UnsafePathError, resolve_within_workspace

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
MAX_WRITE_CHARS = 20000


class FileWriterInput(BaseModel):
    filename: str = Field(description="Filename only (no directories), e.g. 'result.txt'.")
    content: str = Field(description="Text content to write.")

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if not _SAFE_FILENAME_RE.match(value):
            raise ValueError(
                "filename must contain only letters, digits, '.', '_', '-' and no path separators"
            )
        return value


class FileWriterTool(Tool):
    name = "write_file"
    description = (
        "Write text content to a file in the sandboxed workspace directory. "
        "Use this to save final outputs the goal asks for. Filename must have no directories."
    )
    input_model = FileWriterInput

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def _execute(self, parsed_input: FileWriterInput) -> ToolResult:
        if len(parsed_input.content) > MAX_WRITE_CHARS:
            return ToolResult(
                success=False,
                error=f"Content too large ({len(parsed_input.content)} chars, max {MAX_WRITE_CHARS}).",
            )

        try:
            path = resolve_within_workspace(self.workspace_dir, parsed_input.filename)
        except UnsafePathError as exc:
            return ToolResult(success=False, error=str(exc))

        try:
            path.write_text(parsed_input.content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not write file: {exc}")

        return ToolResult(
            success=True,
            output={
                "path": parsed_input.filename,
                "bytes_written": len(parsed_input.content.encode("utf-8")),
            },
        )
