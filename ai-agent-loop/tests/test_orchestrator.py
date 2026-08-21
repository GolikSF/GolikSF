"""End-to-end orchestrator tests driven entirely by a FakeLLMClient (no
network calls). These exercise the real loop control flow, the real
CalculatorTool/FileWriterTool, and real state/persistence code."""

from agent.orchestrator import Orchestrator
from agent.schemas import (
    ActionDecision,
    EvaluationOutput,
    FinalAnswerOutput,
    GoalInterpretation,
    ReplanOutput,
)
from agent.tools import build_default_registry


def make_orchestrator(fake_llm, workspace_dir, runs_dir, max_iterations=10):
    registry = build_default_registry(workspace_dir, search_api_key=None)
    return Orchestrator(
        llm_client=fake_llm, tool_registry=registry, runs_dir=runs_dir, max_iterations=max_iterations
    )


def test_stops_on_success_and_observation_influences_next_action(fake_llm_factory, workspace_dir, runs_dir):
    script = {
        "submit_plan": [
            GoalInterpretation(
                interpretation="compute a total with tax",
                success_criteria=["subtotal and tax-inclusive total are both computed"],
                initial_plan=["compute subtotal", "apply tax"],
            )
        ],
        "select_action": [
            ActionDecision(
                action_type="TOOL",
                thought="compute subtotal",
                tool_name="calculator",
                tool_input={"expression": "17 * 23.50"},
            ),
            ActionDecision(
                action_type="TOOL",
                thought="apply tax to the subtotal found previously",
                tool_name="calculator",
                tool_input={"expression": "399.5 * 1.0825"},
            ),
        ],
        "submit_evaluation": [
            EvaluationOutput(
                success=True,
                progress_score=50,
                confidence=0.5,
                unresolved_questions=[],
                problems=[],
                recommended_next_step="apply tax",
                should_continue=True,
                reason="subtotal done, tax still needed",
            ),
            EvaluationOutput(
                success=True,
                progress_score=100,
                confidence=0.95,
                unresolved_questions=[],
                problems=[],
                recommended_next_step="none",
                should_continue=False,
                reason="total with tax computed, success criteria satisfied",
            ),
        ],
        "submit_final_answer": [
            FinalAnswerOutput(
                final_answer="The total including tax is 432.46.",
                known_information=["subtotal = 399.5", "total with tax = 432.46"],
            )
        ],
    }
    fake_llm = fake_llm_factory(script)
    orchestrator = make_orchestrator(fake_llm, workspace_dir, runs_dir)

    state = orchestrator.run("Calculate the total cost of 17 items at $23.50 with 8.25% tax.")

    assert state.status == "completed"
    assert state.iteration == 2
    assert "432.46" in state.final_answer

    # The second select_action call must have actually received the subtotal
    # discovered in iteration 1 -- proof that observations from a previous
    # iteration influence later action selection, not just repeated blindly.
    second_action_call = [c for c in fake_llm.calls if c["tool_name"] == "select_action"][1]
    assert "399.5" in second_action_call["user_content"]


def test_stops_at_max_iterations(fake_llm_factory, workspace_dir, runs_dir):
    never_done_eval = EvaluationOutput(
        success=False,
        progress_score=20,
        confidence=0.2,
        unresolved_questions=["still unclear"],
        problems=[],
        recommended_next_step="keep trying",
        should_continue=True,
        reason="not enough progress yet",
    )
    script = {
        "submit_plan": [
            GoalInterpretation(interpretation="i", success_criteria=["c"], initial_plan=["step"])
        ],
        "select_action": [
            ActionDecision(action_type="THINK", thought=f"thinking round {i}") for i in range(1, 4)
        ],
        "submit_evaluation": [never_done_eval, never_done_eval, never_done_eval],
        "submit_final_answer": [FinalAnswerOutput(final_answer="Could not finish in time.")],
    }
    fake_llm = fake_llm_factory(script)
    orchestrator = make_orchestrator(fake_llm, workspace_dir, runs_dir, max_iterations=3)

    state = orchestrator.run("An open-ended goal")

    assert state.status == "stopped_max_iterations"
    assert state.iteration == 3
    assert state.final_answer  # synthesized even without explicit FINAL


def test_duplicate_action_forces_replan_then_terminates_when_stuck(fake_llm_factory, workspace_dir, runs_dir):
    duplicate_action = ActionDecision(
        action_type="TOOL",
        thought="try the same lookup again",
        tool_name="calculator",
        tool_input={"expression": "10 / 2"},
    )
    eval_after_block = EvaluationOutput(
        success=False,
        progress_score=10,
        confidence=0.1,
        unresolved_questions=[],
        problems=["repeated action"],
        recommended_next_step="try something different",
        should_continue=True,
        reason="blocked duplicate, no progress",
    )
    script = {
        "submit_plan": [
            GoalInterpretation(interpretation="i", success_criteria=["c"], initial_plan=["step"])
        ],
        # Same exact TOOL action chosen every time, including after replans.
        "select_action": [duplicate_action.model_copy() for _ in range(4)],
        "submit_evaluation": [eval_after_block.model_copy() for _ in range(4)],
        "submit_replan": [
            ReplanOutput(rationale="try again differently", revised_plan=["different step"]),
            ReplanOutput(rationale="try again differently", revised_plan=["different step"]),
        ],
        "submit_final_answer": [FinalAnswerOutput(final_answer="Gave up after repeated duplicate actions.")],
    }
    fake_llm = fake_llm_factory(script)
    orchestrator = make_orchestrator(fake_llm, workspace_dir, runs_dir, max_iterations=20)

    state = orchestrator.run("A goal that leads the model to repeat itself")

    assert state.status == "stopped_stuck"
    assert state.iteration == 4  # 1 normal attempt + 3 blocked duplicates
    assert len(state.replans) == 2


def test_replanning_updates_plan(fake_llm_factory, workspace_dir, runs_dir):
    script = {
        "submit_plan": [
            GoalInterpretation(interpretation="i", success_criteria=["c"], initial_plan=["original step"])
        ],
        "select_action": [
            ActionDecision(action_type="REPLAN", thought="the original plan won't work"),
        ],
        "submit_replan": [
            ReplanOutput(
                rationale="original plan was invalid", revised_plan=["better step 1", "better step 2"]
            ),
        ],
        "submit_evaluation": [
            EvaluationOutput(
                success=False,
                progress_score=10,
                confidence=0.2,
                unresolved_questions=[],
                problems=[],
                recommended_next_step="follow new plan",
                should_continue=False,
                reason="stopping early for this test",
            )
        ],
    }
    fake_llm = fake_llm_factory(script)
    orchestrator = make_orchestrator(fake_llm, workspace_dir, runs_dir)

    state = orchestrator.run("A goal needing a plan change")

    assert state.plan == ["better step 1", "better step 2"]
    assert state.plan_version == 2
    assert len(state.replans) == 1


def test_model_provided_final_answer_is_accepted_when_evaluator_agrees(
    fake_llm_factory, workspace_dir, runs_dir
):
    script = {
        "submit_plan": [
            GoalInterpretation(interpretation="i", success_criteria=["c"], initial_plan=["step"])
        ],
        "select_action": [
            ActionDecision(action_type="FINAL", thought="done", final_answer="The answer is 42."),
        ],
        "submit_evaluation": [
            EvaluationOutput(
                success=True,
                progress_score=100,
                confidence=0.9,
                unresolved_questions=[],
                problems=[],
                recommended_next_step="none",
                should_continue=False,
                reason="criteria met",
            )
        ],
    }
    fake_llm = fake_llm_factory(script)
    orchestrator = make_orchestrator(fake_llm, workspace_dir, runs_dir)

    state = orchestrator.run("Answer a simple question")

    assert state.status == "completed"
    assert state.final_answer == "The answer is 42."
    # No submit_final_answer call needed since the model's FINAL was accepted.
    assert not any(c["tool_name"] == "submit_final_answer" for c in fake_llm.calls)


def test_model_provided_final_answer_rejected_when_evaluator_disagrees(
    fake_llm_factory, workspace_dir, runs_dir
):
    script = {
        "submit_plan": [
            GoalInterpretation(interpretation="i", success_criteria=["c"], initial_plan=["step"])
        ],
        "select_action": [
            ActionDecision(action_type="FINAL", thought="I think I'm done", final_answer="Guessing: 42."),
            ActionDecision(action_type="THINK", thought="let me actually verify"),
        ],
        "submit_evaluation": [
            EvaluationOutput(
                success=False,
                progress_score=20,
                confidence=0.1,
                unresolved_questions=["is 42 actually correct?"],
                problems=["insufficient evidence"],
                recommended_next_step="verify with a tool",
                should_continue=True,
                reason="no evidence supports this answer",
            ),
            EvaluationOutput(
                success=True,
                progress_score=100,
                confidence=0.9,
                unresolved_questions=[],
                problems=[],
                recommended_next_step="none",
                should_continue=False,
                reason="now verified",
            ),
        ],
    }
    fake_llm = fake_llm_factory(script)
    orchestrator = make_orchestrator(fake_llm, workspace_dir, runs_dir)

    state = orchestrator.run("Answer a simple question")

    assert state.iteration == 2  # first FINAL was rejected, loop continued
    assert state.status == "completed"
    assert "no evidence supports this answer" in state.last_rejected_final
