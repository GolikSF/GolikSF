"""Pydantic schemas for every structured (validated) LLM output.

Every point where the agent asks the model for a decision uses one of these
schemas, enforced via Anthropic's forced tool-use, so we never depend on
fragile natural-language parsing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ActionType = Literal["THINK", "TOOL", "REPLAN", "FINAL"]


class GoalInterpretation(BaseModel):
    """Initial understanding of the goal, produced once at the start of a run."""

    interpretation: str = Field(description="Restate the goal in your own words, clarifying scope.")
    success_criteria: list[str] = Field(
        description="Concrete, checkable conditions that must hold for the goal to be considered done."
    )
    initial_plan: list[str] = Field(description="Ordered list of concrete steps to work toward the goal.")


class ReplanOutput(BaseModel):
    """Output of a replanning step, triggered when the current plan is invalidated."""

    rationale: str = Field(description="Why the previous plan needed to change.")
    revised_plan: list[str] = Field(description="The new ordered list of steps.")
    updated_success_criteria: list[str] | None = Field(
        default=None,
        description="Only set if the success criteria themselves need revising.",
    )


class ActionDecision(BaseModel):
    """A single structured decision about what to do next."""

    action_type: ActionType = Field(
        description=(
            "THINK: reason/synthesize without a tool. TOOL: call a registered tool. "
            "REPLAN: the current plan is invalid or blocked and needs revision. "
            "FINAL: success criteria are satisfied by evidence gathered so far."
        )
    )
    thought: str = Field(description="One or two sentences justifying this choice. Visible to the user.")
    tool_name: str | None = Field(default=None, description="Required when action_type is TOOL.")
    tool_input: dict[str, Any] | None = Field(
        default=None,
        description="Arguments for the tool, matching its input schema. Required when action_type is TOOL.",
    )
    final_answer: str | None = Field(
        default=None, description="Required when action_type is FINAL: the complete answer to the goal."
    )


class EvaluationOutput(BaseModel):
    """Structured evaluation of the most recent action/observation."""

    success: bool = Field(description="Whether the previous action succeeded on its own terms.")
    progress_score: int = Field(ge=0, le=100, description="Overall progress toward the goal, 0-100.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence that the goal is/will be satisfied.")
    unresolved_questions: list[str] = Field(default_factory=list)
    problems: list[str] = Field(
        default_factory=list,
        description="Concrete problems: bad strategy, missing info, wrong tool, tool failure, "
        "repeated action, contradictory evidence, insufficient evidence, impossible requirement.",
    )
    recommended_next_step: str = Field(description="Concrete suggestion for what to do next.")
    should_continue: bool = Field(description="Whether another iteration is worth its cost.")
    reason: str = Field(description="Short justification for should_continue.")


class FinalAnswerOutput(BaseModel):
    """Synthesized final answer, produced from accumulated state when the loop stops
    without the model itself emitting a FINAL action."""

    final_answer: str = Field(description="Direct, complete answer to the original goal.")
    known_information: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
