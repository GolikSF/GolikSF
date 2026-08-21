from agent.state import ActionRecord, AgentState, action_signature


def test_state_initialization():
    state = AgentState(goal="do a thing", max_iterations=5)
    assert state.goal == "do a thing"
    assert state.max_iterations == 5
    assert state.iteration == 0
    assert state.status == "running"
    assert state.final_answer is None
    assert state.run_id  # generated


def test_add_observation_tracks_consecutive_failures():
    state = AgentState(goal="g", max_iterations=5)
    from agent.state import ObservationRecord

    state.add_observation(ObservationRecord(iteration=1, success=False, summary="boom"))
    state.add_observation(ObservationRecord(iteration=2, success=False, summary="boom again"))
    assert state.consecutive_tool_failures == 2
    assert len(state.errors) == 2

    state.add_observation(ObservationRecord(iteration=3, success=True, summary="ok"))
    assert state.consecutive_tool_failures == 0


def test_add_finding_dedupes():
    state = AgentState(goal="g", max_iterations=5)
    state.add_finding("result is 42")
    state.add_finding("result is 42")
    assert state.findings == ["result is 42"]


def test_apply_replan_updates_plan_but_does_not_alone_clear_stuck_counter():
    # Replanning by itself doesn't prove the agent is unstuck -- only a
    # genuinely productive follow-up action does (note_productive_iteration).
    # Otherwise a duplicate-action loop could never accumulate toward
    # termination, since a replan is triggered on every blocked duplicate.
    state = AgentState(goal="g", max_iterations=5)
    state.stuck_counter = 2
    state.apply_replan("old plan failed", ["step a", "step b"], None)
    assert state.plan == ["step a", "step b"]
    assert state.plan_version == 1
    assert state.stuck_counter == 2
    assert len(state.replans) == 1

    state.note_productive_iteration()
    assert state.stuck_counter == 0


def test_consecutive_repeat_count():
    state = AgentState(goal="g", max_iterations=5)
    sig = action_signature("TOOL", "calculator", {"expression": "1+1"})
    other_sig = action_signature("TOOL", "calculator", {"expression": "2+2"})

    assert state.consecutive_repeat_count(sig) == 0

    state.add_action(ActionRecord(iteration=1, action_type="TOOL", thought="t", signature=sig))
    assert state.consecutive_repeat_count(sig) == 1

    state.add_action(ActionRecord(iteration=2, action_type="TOOL", thought="t", signature=sig))
    assert state.consecutive_repeat_count(sig) == 2

    state.add_action(ActionRecord(iteration=3, action_type="TOOL", thought="t", signature=other_sig))
    assert state.consecutive_repeat_count(sig) == 0
    assert state.consecutive_repeat_count(other_sig) == 1


def test_build_prompt_context_includes_key_fields():
    state = AgentState(goal="calculate stuff", max_iterations=5)
    state.interpretation = "compute a total"
    state.success_criteria = ["total is computed"]
    state.plan = ["use calculator"]
    state.add_finding("subtotal is 100")

    ctx = state.build_prompt_context()
    assert "calculate stuff" in ctx
    assert "compute a total" in ctx
    assert "total is computed" in ctx
    assert "use calculator" in ctx
    assert "subtotal is 100" in ctx


def test_to_dict_is_json_serializable():
    import json

    state = AgentState(goal="g", max_iterations=5)
    state.add_finding("x")
    payload = state.to_dict()
    json.dumps(payload)  # must not raise
    assert payload["goal"] == "g"
