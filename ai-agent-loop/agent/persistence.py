"""Run persistence.

Writes each run as a JSON snapshot to `runs/<run_id>.json`, and also appends
a JSONL event log (`runs/<run_id>.events.jsonl`) live as the run progresses,
so a crash mid-run still leaves a readable trail rather than losing
everything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.state import AgentState, _now


class RunLogger:
    def __init__(self, runs_dir: Path, run_id: str) -> None:
        self.runs_dir = runs_dir
        self.run_id = run_id
        self.events_path = runs_dir / f"{run_id}.events.jsonl"
        self.snapshot_path = runs_dir / f"{run_id}.json"

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {"timestamp": _now(), "type": event_type, **payload}
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def save_snapshot(self, state: AgentState) -> Path:
        self.snapshot_path.write_text(state.to_json(), encoding="utf-8")
        return self.snapshot_path


def load_run(runs_dir: Path, run_id: str) -> dict:
    path = runs_dir / f"{run_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))
