import json

from agent.persistence import RunLogger, load_run
from agent.state import AgentState


def test_run_logger_writes_events_and_snapshot(runs_dir):
    state = AgentState(goal="test goal", max_iterations=3, run_id="testrun1")
    logger = RunLogger(runs_dir, state.run_id)

    logger.log_event("plan", {"interpretation": "x"})
    logger.log_event("action", {"action_type": "TOOL"})

    state.final_answer = "42"
    state.status = "completed"
    logger.save_snapshot(state)

    assert (runs_dir / "testrun1.events.jsonl").exists()
    assert (runs_dir / "testrun1.json").exists()

    lines = (runs_dir / "testrun1.events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    first_event = json.loads(lines[0])
    assert first_event["type"] == "plan"

    loaded = load_run(runs_dir, "testrun1")
    assert loaded["goal"] == "test goal"
    assert loaded["final_answer"] == "42"
    assert loaded["status"] == "completed"
