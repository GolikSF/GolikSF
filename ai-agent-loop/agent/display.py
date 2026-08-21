"""Console observability. Prints a concise, readable trace of the loop
without ever exposing hidden chain-of-thought -- only the short, structured
`thought` field the model is asked to produce alongside its decision."""

from __future__ import annotations

from agent.schemas import ActionDecision, EvaluationOutput
from agent.state import AgentState


def _rule(char: str = "-", width: int = 60) -> str:
    return char * width


def print_goal(goal: str) -> None:
    print(_rule("="))
    print(f"GOAL: {goal}")
    print(_rule("="))


def print_plan(state: AgentState) -> None:
    print(f"\nInterpretation: {state.interpretation}")
    print("Success criteria:")
    for c in state.success_criteria:
        print(f"  - {c}")
    print(f"Plan (v{state.plan_version}):")
    for i, step in enumerate(state.plan, 1):
        print(f"  {i}. {step}")


def print_iteration_header(state: AgentState) -> None:
    print(f"\n{_rule()}")
    print(f"[Iteration {state.iteration}/{state.max_iterations}]")


def print_action(action: ActionDecision) -> None:
    print(f"\nAction: {action.action_type}")
    print(f"  {action.thought}")
    if action.action_type == "TOOL":
        print(f"  Tool: {action.tool_name}({action.tool_input})")


def print_observation(observation) -> None:
    status = "ok" if observation.success else "FAILED"
    print(f"\nObservation ({status}): {observation.summary}")


def print_evaluation(evaluation: EvaluationOutput) -> None:
    print("\nEvaluation:")
    print(f"  Progress: {evaluation.progress_score}%")
    print(f"  Confidence: {evaluation.confidence:.2f}")
    if evaluation.problems:
        print(f"  Problems: {', '.join(evaluation.problems)}")
    if evaluation.unresolved_questions:
        print(f"  Unresolved: {', '.join(evaluation.unresolved_questions)}")
    print(f"  Next step: {evaluation.recommended_next_step}")


def print_decision(should_continue: bool, reason: str) -> None:
    print(f"\nDecision: {'Continue' if should_continue else 'Stop'} -- {reason}")


def print_replan(rationale: str, plan: list[str]) -> None:
    print(f"\nReplanning: {rationale}")
    for i, step in enumerate(plan, 1):
        print(f"  {i}. {step}")


def print_final(state: AgentState) -> None:
    print(f"\n{_rule('=')}")
    print(f"FINAL ANSWER (status={state.status})")
    print(_rule("="))
    print(state.final_answer)
    print(f"\nRun saved: runs/{state.run_id}.json")
