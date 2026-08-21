"""Shared path-safety helper for the file-reader and file-writer tools.

Both tools are restricted to a single workspace directory. This resolves a
model-supplied relative path and rejects anything that would escape the
workspace (path traversal, absolute paths outside it, symlink tricks).
"""

from __future__ import annotations

from pathlib import Path


class UnsafePathError(ValueError):
    pass


def resolve_within_workspace(workspace_dir: Path, relative_path: str) -> Path:
    if not relative_path or relative_path.strip() == "":
        raise UnsafePathError("Path must not be empty.")

    candidate = (workspace_dir / relative_path).resolve()
    workspace_resolved = workspace_dir.resolve()

    try:
        candidate.relative_to(workspace_resolved)
    except ValueError:
        raise UnsafePathError(
            f"Path '{relative_path}' resolves outside the workspace directory and is not allowed."
        ) from None

    return candidate
