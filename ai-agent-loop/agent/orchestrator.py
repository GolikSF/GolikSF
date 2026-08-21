"""The agent orchestrator: a real, application-code-controlled loop.

GOAL -> PLAN -> CHOOSE ACTION -> ACT -> OBSERVE -> EVALUATE -> REFLECT/REPLAN
-> REPEAT IF NECESSARY -> FINAL ANSWER

Every iteration of this loop is a plain Python `while` loop step. The LLM is
only ever consulted for one bounded, structured decision at a time (plan,
choose action, evaluate, replan, synthesize final answer). The application
code -- not the model -- decides whether the loop continues.
"""

from __future__ import annotations

import logging
from pathlib import Path

from agent import display
from agent.llm_client import LLMClient, LLMOutputError
from agent.persistence import RunLogger
from agent.schemas import (
    ActionDecision,
    EvaluationOutput,
    FinalAnswerOutput,
    GoalInterpretation,
    ReplanOutput,
)
from agent.state import (
    ActionRecord,
    AgentState,
    EvaluationRecord,
    ObservationRecord,
    action_signature,
)
from agent.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

# Stopping thresholds. Deliberately conservative and centralized here so the
# "when do we stop" policy lives in one obvious place.
HIGH_CONFIDENCE_STOP = 0.9
HIGH_PROGRESS_STOP = 90
MAX_STUCK_REPLANS = 2
MAX_CONSECUTIVE_TOOL_FAILURES = 3

PLAN_SYSTEM_PROMPT = """You are the planning module of an autonomous agent. \
Given a user's goal, interpret it precisely, define concrete success criteria \
that can later be checked against evidence, and produce a short ordered plan \
of concrete steps. Keep the plan to at most 6 steps. Do not solve the goal here."""

REPLAN_SYSTEM_PROMPT = """You are the replanning module of an autonomous agent. \
The current plan has been invalidated, blocked, or exhausted. Given the goal, \
findings so far, and problems encountered, produce a revised plan that avoids \
repeating the same mistakes. Be concrete and specific about what changes."""

ACTION_SYSTEM_PROMPT = """You are the decision-making module of an autonomous agent \
executing one step at a time. Given the current state, choose exactly one next action:
- THINK: reason or synthesize using only information already gathered, no tool.
- TOOL: call one of the available tools to gather information or produce output.
- REPLAN: the current plan is invalidated, blocked, or exhausted; produce a new direction \
(the actual new plan is generated in a separate step -- here just decide to replan and say why).
- FINAL: the success criteria are satisfied by the evidence gathered so far; provide the complete final answer.

Available tools:
{tools}

Never repeat a tool call with the same arguments you already tried unless new information \
would change its outcome. Prefer TOOL over THINK when a tool can produce concrete evidence."""

EVAL_SYSTEM_PROMPT = """You are the evaluation module of an autonomous agent. Given the most \
recent action and its observation, in the context of the overall goal, assess progress honestly \
and skeptically. Do not assume success without evidence. Flag contradictions, missing information, \
and repeated unproductive actions. Recommend whether continuing is worth the cost."""

FINAL_SYSTEM_PROMPT = """You are the final-answer module of an autonomous agent whose working \
loop has ended. Synthesize a complete, direct answer to the original goal using ONLY the \
findings, actions, and observations provided. Clearly separate known information (backed by \
tool output), assumptions, uncertainties, and unresolved issues. Do not invent facts."""


class Orchestrator:
    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        runs_dir: Path,
        max_iterations: int = 10,
    ) -> None:
        self.llm = llm_client
        self.tools = tool_registry
        self.runs_dir = runs_dir
        self.max_iterations = max_iterations

    # -- public entry point -------------------------------------------------

    def run(self, goal: str) -> AgentState:
        state = AgentState(goal=goal, max_iterations=self.max_iterations)
        run_logger = RunLogger(self.runs_dir, state.run_id)

        display.print_goal(goal)
        self._plan(state, run_logger)
        display.print_plan(state)

        while True:
            if state.iteration >= state.max_iterations:
                state.status = "stopped_max_iterations"
                state.stop_reason = f"Reached maximum iterations ({state.max_iterations})."
                break

            state.iteration += 1
            display.print_iteration_header(state)

            action = self._choose_action(state)
            display.print_action(action)
            run_logger.log_event("action", {"iteration": state.iteration, **action.model_dump()})

            sig = action_signature(action.action_type, action.tool_name, action.tool_input)
            repeat_count = state.consecutive_repeat_count(sig) if action.action_type == "TOOL" else 0
            blocked_duplicate = repeat_count >= 1

            action_record = ActionRecord(
                iteration=state.iteration,
                action_type=action.action_type,
                thought=action.thought,
                tool_name=action.tool_name,
                tool_input=action.tool_input,
                final_answer=action.final_answer,
                signature=sig,
            )
            state.add_action(action_record)

            if blocked_duplicate:
                observation = ObservationRecord(
                    iteration=state.iteration,
                    success=False,
                    summary=(
                        f"Blocked: identical tool call ({action.tool_name}) with the same arguments "
                        "was already attempted with no new information. Forcing reconsideration."
                    ),
                )
                state.stuck_counter += 1
            else:
                observation = self._act(state, action)
                if observation.success:
                    state.note_productive_iteration()

            state.add_observation(observation)
            display.print_observation(observation)
            run_logger.log_event(
                "observation",
                {
                    "iteration": state.iteration,
                    "success": observation.success,
                    "summary": observation.summary,
                },
            )

            if observation.success and action.action_type in ("TOOL", "THINK") and observation.summary:
                state.add_finding(f"[iter {state.iteration}] {observation.summary}")

            if action.action_type == "REPLAN" and not blocked_duplicate:
                self._replan(state, run_logger, rationale_hint=action.thought)

            evaluation = self._evaluate(state, action, observation)
            state.add_evaluation(
                EvaluationRecord(
                    iteration=state.iteration,
                    success=evaluation.success,
                    progress_score=evaluation.progress_score,
                    confidence=evaluation.confidence,
                    unresolved_questions=evaluation.unresolved_questions,
                    problems=evaluation.problems,
                    recommended_next_step=evaluation.recommended_next_step,
                    should_continue=evaluation.should_continue,
                    reason=evaluation.reason,
                )
            )
            display.print_evaluation(evaluation)
            run_logger.log_event("evaluation", {"iteration": state.iteration, **evaluation.model_dump()})

            stop, status, reason = self._check_stopping_conditions(
                state, action, evaluation, blocked_duplicate
            )
            display.print_decision(not stop, reason)

            if stop:
                state.status = status
                state.stop_reason = reason
                if action.action_type == "FINAL" and status == "completed":
                    state.final_answer = action.final_answer
                break

            if action.action_type == "FINAL":
                # Model claimed done but the evaluator disagreed: reject and continue.
                state.last_rejected_final = evaluation.reason
                state.errors.append(
                    f"[iter {state.iteration}] FINAL answer rejected by evaluator: {evaluation.reason}"
                )

            if blocked_duplicate and state.stuck_counter >= 1:
                self._replan(state, run_logger, rationale_hint="Recovering from a blocked duplicate action.")

        if state.final_answer is None:
            self._synthesize_final_answer(state)

        run_logger.save_snapshot(state)
        display.print_final(state)
        return state

    # -- loop stages ----------------------------------------------------------

    def _plan(self, state: AgentState, run_logger: RunLogger) -> None:
        result: GoalInterpretation = self.llm.call_structured(
            system=PLAN_SYSTEM_PROMPT,
            user_content=f"Goal: {state.goal}",
            output_model=GoalInterpretation,
            tool_name="submit_plan",
            tool_description="Submit the goal interpretation, success criteria, and initial plan.",
        )
        state.interpretation = result.interpretation
        state.success_criteria = result.success_criteria
        state.plan = result.initial_plan
        state.plan_version = 1
        run_logger.log_event("plan", result.model_dump())

    def _choose_action(self, state: AgentState) -> ActionDecision:
        system = ACTION_SYSTEM_PROMPT.format(tools=self.tools.describe_all())
        return self.llm.call_structured(
            system=system,
            user_content=state.build_prompt_context(),
            output_model=ActionDecision,
            tool_name="select_action",
            tool_description="Select and justify the single next action to take.",
        )

    def _act(self, state: AgentState, action: ActionDecision) -> ObservationRecord:
        if action.action_type == "THINK":
            return ObservationRecord(iteration=state.iteration, success=True, summary=action.thought)

        if action.action_type == "REPLAN":
            return ObservationRecord(
                iteration=state.iteration, success=True, summary="Plan revision requested; replanning."
            )

        if action.action_type == "FINAL":
            return ObservationRecord(
                iteration=state.iteration,
                success=True,
                summary=f"Proposed final answer: {(action.final_answer or '')[:300]}",
            )

        # TOOL
        if not action.tool_name:
            return ObservationRecord(
                iteration=state.iteration,
                success=False,
                summary="Action was TOOL but no tool_name was given.",
            )
        tool = self.tools.get(action.tool_name)
        if tool is None:
            return ObservationRecord(
                iteration=state.iteration,
                success=False,
                summary=f"Unknown tool '{action.tool_name}'. Available: {self.tools.names()}",
            )
        result = tool.run(action.tool_input or {})
        return ObservationRecord(
            iteration=state.iteration, success=result.success, summary=result.summary(), raw=result.output
        )

    def _evaluate(
        self, state: AgentState, action: ActionDecision, observation: ObservationRecord
    ) -> EvaluationOutput:
        context = state.build_prompt_context()
        context += f"\n\nMOST RECENT ACTION: {action.action_type} - {action.thought}"
        context += (
            f"\nMOST RECENT OBSERVATION ({'ok' if observation.success else 'failed'}): {observation.summary}"
        )
        return self.llm.call_structured(
            system=EVAL_SYSTEM_PROMPT,
            user_content=context,
            output_model=EvaluationOutput,
            tool_name="submit_evaluation",
            tool_description="Submit a structured evaluation of progress so far.",
        )

    def _replan(self, state: AgentState, run_logger: RunLogger, rationale_hint: str) -> None:
        context = state.build_prompt_context()
        context += f"\n\nREPLAN TRIGGER: {rationale_hint}"
        result: ReplanOutput = self.llm.call_structured(
            system=REPLAN_SYSTEM_PROMPT,
            user_content=context,
            output_model=ReplanOutput,
            tool_name="submit_replan",
            tool_description="Submit a revised plan.",
        )
        state.apply_replan(result.rationale, result.revised_plan, result.updated_success_criteria)
        display.print_replan(result.rationale, result.revised_plan)
        run_logger.log_event("replan", result.model_dump())

    def _check_stopping_conditions(
        self, state: AgentState, action: ActionDecision, evaluation: EvaluationOutput, blocked_duplicate: bool
    ) -> tuple[bool, str, str]:
        """Returns (should_stop, status, reason). This is application code,
        not the model, making the final call."""

        if action.action_type == "FINAL" and evaluation.success and evaluation.confidence >= 0.5:
            return True, "completed", "Success criteria satisfied; model-provided final answer accepted."

        if evaluation.success and not evaluation.should_continue:
            return True, "completed", evaluation.reason or "Evaluator reports success criteria satisfied."

        if evaluation.confidence >= HIGH_CONFIDENCE_STOP and evaluation.progress_score >= HIGH_PROGRESS_STOP:
            return True, "completed", "High confidence and progress reached threshold."

        if state.stuck_counter > MAX_STUCK_REPLANS:
            return (
                True,
                "stopped_stuck",
                "Repeated duplicate actions with no new information; no productive alternative found.",
            )

        if state.consecutive_tool_failures >= MAX_CONSECUTIVE_TOOL_FAILURES:
            return (
                True,
                "stopped_tool_failures",
                (
                    f"{state.consecutive_tool_failures} consecutive tool failures; further attempts unlikely to help."
                ),
            )

        if not evaluation.should_continue:
            return (
                True,
                "stopped_low_value",
                evaluation.reason or "Evaluator judged further iteration low-value.",
            )

        if state.iteration >= state.max_iterations:
            return True, "stopped_max_iterations", f"Reached maximum iterations ({state.max_iterations})."

        return (
            False,
            "running",
            evaluation.recommended_next_step or "Continuing per evaluator recommendation.",
        )

    def _synthesize_final_answer(self, state: AgentState) -> None:
        context = state.build_prompt_context()
        context += f"\n\nThe loop ended with status={state.status} ({state.stop_reason})."
        try:
            result: FinalAnswerOutput = self.llm.call_structured(
                system=FINAL_SYSTEM_PROMPT,
                user_content=context,
                output_model=FinalAnswerOutput,
                tool_name="submit_final_answer",
                tool_description="Submit the synthesized final answer.",
            )
        except LLMOutputError as exc:
            logger.warning("Failed to synthesize final answer: %s", exc)
            state.final_answer = (
                "The agent could not produce a validated final answer. "
                f"Run stopped with status={state.status} ({state.stop_reason}). "
                f"Findings gathered: {state.findings}"
            )
            return

        parts = [result.final_answer]
        if result.known_information:
            parts.append("\nKnown information:\n" + "\n".join(f"- {x}" for x in result.known_information))
        if result.assumptions:
            parts.append("\nAssumptions:\n" + "\n".join(f"- {x}" for x in result.assumptions))
        if result.uncertainties:
            parts.append("\nUncertainties:\n" + "\n".join(f"- {x}" for x in result.uncertainties))
        if result.unresolved_issues:
            parts.append("\nUnresolved issues:\n" + "\n".join(f"- {x}" for x in result.unresolved_issues))
        state.final_answer = "\n".join(parts)
