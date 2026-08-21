"""Environment-based configuration for the agent.

All configuration comes from environment variables (optionally loaded from a
local .env file). Nothing is ever hardcoded, and secrets are never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (avoids taking on a hard python-dotenv dependency
    at import time if it's ever missing, though it is also listed in
    requirements.txt)."""
    try:
        from dotenv import load_dotenv

        load_dotenv(path)
    except ImportError:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(PROJECT_ROOT / ".env")


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    model: str
    max_iterations: int
    workspace_dir: Path
    runs_dir: Path
    search_api_key: str | None
    request_timeout: float

    @staticmethod
    def load() -> Config:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise ConfigError(
                "Missing required configuration: ANTHROPIC_API_KEY.\n"
                "Set it in a .env file (see .env.example) or export it in your shell:\n"
                "  export ANTHROPIC_API_KEY=sk-ant-...\n"
                "Get a key at https://console.anthropic.com/settings/keys"
            )

        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929").strip()

        try:
            max_iterations = int(os.environ.get("MAX_ITERATIONS", "10"))
        except ValueError as exc:
            raise ConfigError("MAX_ITERATIONS must be an integer.") from exc
        if max_iterations < 1:
            raise ConfigError("MAX_ITERATIONS must be at least 1.")

        workspace_dir = Path(os.environ.get("WORKSPACE_DIR", str(PROJECT_ROOT / "workspace")))
        runs_dir = Path(os.environ.get("RUNS_DIR", str(PROJECT_ROOT / "runs")))
        workspace_dir.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)

        search_api_key = os.environ.get("SEARCH_API_KEY", "").strip() or None

        try:
            request_timeout = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "60"))
        except ValueError as exc:
            raise ConfigError("REQUEST_TIMEOUT_SECONDS must be a number.") from exc

        return Config(
            anthropic_api_key=api_key,
            model=model,
            max_iterations=max_iterations,
            workspace_dir=workspace_dir.resolve(),
            runs_dir=runs_dir.resolve(),
            search_api_key=search_api_key,
            request_timeout=request_timeout,
        )
