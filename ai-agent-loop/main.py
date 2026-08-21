#!/usr/bin/env python3
"""CLI entry point for the autonomous agent loop.

Usage:
    python main.py "Your goal here"
    python main.py --max-iterations 5 "Your goal here"
    python main.py                      # interactive mode, prompts for a goal
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an autonomous AI agent loop toward a goal.")
    parser.add_argument("goal", nargs="?", help="Natural-language goal. If omitted, you'll be prompted.")
    parser.add_argument(
        "--max-iterations", type=int, default=None, help="Override MAX_ITERATIONS from config for this run."
    )
    args = parser.parse_args()

    goal = args.goal
    if not goal:
        try:
            goal = input("Goal: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nNo goal provided. Exiting.")
            return 1
    if not goal:
        print("No goal provided. Exiting.")
        return 1

    # Import after argument parsing so `--help` works even without a valid
    # environment, and config errors are reported cleanly rather than as a
    # raw traceback.
    from agent.config import Config, ConfigError

    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        return 1

    if args.max_iterations is not None:
        config = config.__class__(
            anthropic_api_key=config.anthropic_api_key,
            model=config.model,
            max_iterations=args.max_iterations,
            workspace_dir=config.workspace_dir,
            runs_dir=config.runs_dir,
            search_api_key=config.search_api_key,
            request_timeout=config.request_timeout,
        )

    from agent.llm_client import LLMClient
    from agent.orchestrator import Orchestrator
    from agent.tools import build_default_registry

    llm_client = LLMClient(
        api_key=config.anthropic_api_key, model=config.model, timeout=config.request_timeout
    )
    tool_registry = build_default_registry(config.workspace_dir, config.search_api_key)
    orchestrator = Orchestrator(
        llm_client=llm_client,
        tool_registry=tool_registry,
        runs_dir=config.runs_dir,
        max_iterations=config.max_iterations,
    )

    try:
        orchestrator.run(goal)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
