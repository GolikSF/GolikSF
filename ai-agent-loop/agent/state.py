"""The agent's persistent state.

This is the single object that survives across loop iterations. It holds
everything the orchestrator needs to decide what to do next, and everything
persistence.py needs to write a run to disk. Context sent back to the model
each iteration is a *condensed* view built from this state (see
`build_prompt_context`), not the full raw history, so token usage stays
bounded as a run gets longer.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

RECENT_CONTEXT_WINDOW = 4  # how many past action/observation pairs go verbatim into each prompt
MAX_FINDINGS = 25


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def action_signature(action_type: str, tool_name: str | None, tool_input: dict | None) -> str:
    payload = json.dumps(
        {"action_type": action_type, "tool_name": tool_name, "tool_input": tool_input or {}},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class ActionRecord:
    iteration: int
    action_type: str
    thought: str
    tool_name: str | None = None
    tool_input: dict | None = None
    final_answer: str | None = None
    signature: str = ""
    timestamp: str = field(default_factory=_now)


@dataclass
class ObservationRecord:
    iteration: int
    success: bool
    summary: str
    raw: Any = None
    timestamp: str = field(default_factory=_now)


@dataclass
class EvaluationRecord:
    iteration: int
    success: bool
    progress_score: int
    confidence: float
    unresolved_questions: list[str]
    problems: list[str]
    recommended_next_step: str
    should_continue: bool
    reason: str
    timestamp: str = field(default_factory=_now)


@dataclass
class ReplanRecord:
    iteration: int
    rationale: str
    plan: list[str]
    timestamp: str = field(default_factory=_now)


class AgentState:
    def __init__(self, goal: str, max_iterations: int, run_id: str | None = None) -> None:
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.goal = goal
        self.max_iterations = max_iterations

        self.interpretation: str = ""
        self.success_criteria: list[str] = []
        self.plan: list[str] = []
        self.plan_version: int = 0
        self.replans: list[ReplanRecord] = []

        self.iteration: int = 0
        self.actions: list[ActionRecord] = []
        self.observations: list[ObservationRecord] = []
        self.evaluations: list[EvaluationRecord] = []

        self.findings: list[str] = []
        self.errors: list[str] = []
        self.unresolved_questions: list[str] = []

        self.progress_score: int = 0
        self.confidence: float = 0.0
        self.consecutive_tool_failures: int = 0
        self.stuck_counter: int = 0
        self.last_rejected_final: str | None = None

        self.final_answer: str | None = None
        self.status: str = "running"
        self.stop_reason: str | None = None

        self.created_at = _now()
        self.updated_at = _now()

    # -- mutation helpers -------------------------------------------------

    def touch(self) -> None:
        self.updated_at = _now()

    def add_action(self, record: ActionRecord) -> None:
        self.actions.append(record)
        self.touch()

    def add_observation(self, record: ObservationRecord) -> None:
        self.observations.append(record)
        if record.success:
            self.consecutive_tool_failures = 0
        else:
            self.consecutive_tool_failures += 1
            self.errors.append(f"[iter {record.iteration}] {record.summary}")
        self.touch()

    def add_evaluation(self, record: EvaluationRecord) -> None:
        self.evaluations.append(record)
        self.progress_score = record.progress_score
        self.confidence = record.confidence
        for q in record.unresolved_questions:
            if q not in self.unresolved_questions:
                self.unresolved_questions.append(q)
        self.touch()

    def add_finding(self, text: str) -> None:
        text = text.strip()
        if text and text not in self.findings:
            self.findings.append(text)
            if len(self.findings) > MAX_FINDINGS:
                self.findings.pop(0)
        self.touch()

    def apply_replan(self, rationale: str, plan: list[str], updated_criteria: list[str] | None) -> None:
        self.plan = plan
        self.plan_version += 1
        if updated_criteria:
            self.success_criteria = updated_criteria
        self.replans.append(ReplanRecord(iteration=self.iteration, rationale=rationale, plan=plan))
        self.touch()
        # Note: stuck_counter is deliberately NOT reset here. Replanning alone
        # doesn't prove the agent is unstuck -- only a genuinely new, successful
        # action does (see AgentState.note_productive_iteration).

    def note_productive_iteration(self) -> None:
        """Call when an iteration executes a non-duplicate action successfully.
        This is what actually proves the agent is making progress, so it's the
        only thing allowed to clear the stuck counter."""
        self.stuck_counter = 0

    # -- duplicate-action detection ---------------------------------------

    def consecutive_repeat_count(self, signature: str) -> int:
        """How many times, counting back from the most recent action, this
        exact signature has already appeared consecutively."""
        count = 0
        for record in reversed(self.actions):
            if record.signature == signature:
                count += 1
            else:
                break
        return count

    # -- prompt context building (bounded, not full raw history) ----------

    def build_prompt_context(self) -> str:
        lines: list[str] = []
        lines.append(f"GOAL: {self.goal}")
        if self.interpretation:
            lines.append(f"INTERPRETATION: {self.interpretation}")
        if self.success_criteria:
            lines.append("SUCCESS CRITERIA:")
            lines.extend(f"  - {c}" for c in self.success_criteria)
        if self.plan:
            lines.append(f"CURRENT PLAN (v{self.plan_version}):")
            lines.extend(f"  {i+1}. {step}" for i, step in enumerate(self.plan))

        lines.append(f"ITERATION: {self.iteration}/{self.max_iterations}")

        if self.findings:
            lines.append("ACCUMULATED FINDINGS:")
            lines.extend(f"  - {f}" for f in self.findings)

        recent_actions = self.actions[-RECENT_CONTEXT_WINDOW:]
        if recent_actions:
            lines.append(f"RECENT ACTIVITY (last {len(recent_actions)}):")
            obs_by_iter = {o.iteration: o for o in self.observations}
            for a in recent_actions:
                lines.append(f"  [iter {a.iteration}] ACTION {a.action_type}: {a.thought}")
                if a.tool_name:
                    lines.append(f"      tool={a.tool_name} input={a.tool_input}")
                obs = obs_by_iter.get(a.iteration)
                if obs:
                    status = "ok" if obs.success else "FAILED"
                    lines.append(f"      -> observation ({status}): {obs.summary}")

        if self.evaluations:
            last_eval = self.evaluations[-1]
            lines.append(
                "LAST EVALUATION: "
                f"success={last_eval.success} progress={last_eval.progress_score} "
                f"confidence={last_eval.confidence} should_continue={last_eval.should_continue}"
            )
            lines.append(f"  recommended_next_step: {last_eval.recommended_next_step}")
            if last_eval.problems:
                lines.append(f"  problems: {last_eval.problems}")

        if self.unresolved_questions:
            lines.append(f"UNRESOLVED QUESTIONS: {self.unresolved_questions}")

        if self.last_rejected_final:
            lines.append(
                f"NOTE: A previous FINAL answer was rejected by the evaluator: {self.last_rejected_final}"
            )

        if self.stuck_counter:
            lines.append(
                f"WARNING: {self.stuck_counter} duplicate action(s) were just blocked. "
                "Do not repeat the same tool call with the same input; choose a different action or REPLAN."
            )

        return "\n".join(lines)

    # -- persistence --------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "max_iterations": self.max_iterations,
            "interpretation": self.interpretation,
            "success_criteria": self.success_criteria,
            "plan": self.plan,
            "plan_version": self.plan_version,
            "replans": [r.__dict__ for r in self.replans],
            "iteration": self.iteration,
            "actions": [a.__dict__ for a in self.actions],
            "observations": [o.__dict__ for o in self.observations],
            "evaluations": [e.__dict__ for e in self.evaluations],
            "findings": self.findings,
            "errors": self.errors,
            "unresolved_questions": self.unresolved_questions,
            "progress_score": self.progress_score,
            "confidence": self.confidence,
            "consecutive_tool_failures": self.consecutive_tool_failures,
            "stuck_counter": self.stuck_counter,
            "final_answer": self.final_answer,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)
