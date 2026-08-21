# AI Agent Loop

A small, dependency-light autonomous AI agent built around a real, application-code-controlled
loop: `GOAL -> PLAN -> CHOOSE ACTION -> ACT -> OBSERVE -> EVALUATE -> REFLECT/REPLAN -> REPEAT -> FINAL ANSWER`.

No LangChain, LangGraph, CrewAI, or AutoGen. The loop is a plain Python `while` loop in
`agent/orchestrator.py` — read that file to understand exactly what the agent does on every
iteration. Every decision the model makes is validated, structured output (via Anthropic forced
tool-use + Pydantic), never fragile text parsing.

## What it does

You give it a natural-language goal. It:

1. Asks the model to interpret the goal, define success criteria, and produce an initial plan.
2. Repeatedly: picks one structured action (`THINK`, `TOOL`, `REPLAN`, or `FINAL`), executes it,
   records the observation, and asks the model to evaluate progress (success, progress score,
   confidence, problems, unresolved questions, whether to continue).
3. Uses that evaluation — plus application-code rules, not the model — to decide whether to keep
   going, replan, or stop.
4. Stops for one of several explicit reasons (see [Stopping conditions](#stopping-conditions)) and
   produces a final answer that distinguishes known information from assumptions and uncertainty.

Every run is logged to `runs/` as it happens.

## Architecture

```
main.py                    CLI entry point
agent/
  config.py                 Environment-variable configuration, fails loudly & clearly if missing
  schemas.py                 Pydantic schemas for every structured LLM output
  llm_client.py               Anthropic wrapper: forced tool-use + validation + retry-on-malformed-output
  state.py                     AgentState: everything that persists across iterations
  orchestrator.py               The actual loop. Read this file to understand the agent.
  display.py                     Console observability (prints the trace, never hidden reasoning)
  persistence.py                  Run logging (JSON snapshot + JSONL event stream) to runs/
  tools/
    base.py                        Tool base class + ToolRegistry
    calculator.py                   Safe AST-based arithmetic (no eval())
    file_reader.py                   Sandboxed read-only file tool
    file_writer.py                    Sandboxed file-writing tool
    web_search.py                      Web search tool; cleanly disabled without SEARCH_API_KEY
    workspace_paths.py                 Shared path-traversal protection for file tools
tests/                       Automated tests, no network calls (FakeLLMClient + mocked Anthropic SDK)
workspace/                   Sandbox directory for file_reader/file_writer (gitignored)
runs/                        Per-run JSON/JSONL logs (gitignored)
```

### The agent loop (`agent/orchestrator.py`)

Each iteration is real application code, not a single giant prompt simulating multiple steps:

```python
while True:
    if state.iteration >= state.max_iterations:
        break  # stopping condition, decided in code

    action = self._choose_action(state)          # 1 structured LLM call
    observation = self._act(state, action)         # deterministic Python, executes the tool
    evaluation = self._evaluate(state, action, observation)  # 1 structured LLM call

    stop, status, reason = self._check_stopping_conditions(...)  # pure Python logic
    if stop:
        break
```

The model is only ever asked for one bounded decision at a time. **Application code decides
whether the loop continues** — see `_check_stopping_conditions` in `orchestrator.py`.

### Structured actions

The model must choose exactly one of:

- `THINK` — reason/synthesize using only what's already known, no tool call.
- `TOOL` — call a registered tool with validated arguments.
- `REPLAN` — the current plan is invalidated or blocked; triggers a dedicated replanning call.
- `FINAL` — propose a final answer. **The application code does not blindly trust this** — the
  evaluator still runs, and if it disagrees, the `FINAL` is rejected and the loop continues
  (this is exercised directly in `tests/test_orchestrator.py`).

### Context management

The model never receives the full raw history. `AgentState.build_prompt_context()` builds a
bounded view each iteration: goal, interpretation, success criteria, current plan, accumulated
deduplicated findings (capped), only the last 4 action/observation pairs verbatim, the latest
evaluation, and unresolved questions. This keeps token usage roughly flat as a run gets longer,
while still letting later iterations demonstrably react to what earlier ones discovered.

### Duplicate-action protection

Before executing a `TOOL` action, the orchestrator computes a stable signature (tool name + JSON
of its arguments) and checks whether the *immediately preceding* action(s) have the same
signature. If so, the call is **blocked** (not executed again), a synthetic failure observation is
recorded, and a replan is forced. A separate `stuck_counter` — which only clears when a
genuinely new action subsequently succeeds, not merely because a replan happened — accumulates
across repeated blocks. If it exceeds a threshold, the run terminates with `status=stopped_stuck`
rather than looping forever.

### Stopping conditions

Checked in code (`Orchestrator._check_stopping_conditions`) after every evaluation, in order:

1. Model proposed `FINAL` and the evaluator agrees (success + reasonable confidence) → `completed`.
2. Evaluator says success and no further iteration is worth it → `completed`.
3. Confidence ≥ 0.9 **and** progress ≥ 90 → `completed`.
4. Duplicate-action stuck counter exceeds its threshold → `stopped_stuck`.
5. 3+ consecutive tool failures → `stopped_tool_failures`.
6. Evaluator says continuing isn't worth it → `stopped_low_value`.
7. Max iterations reached → `stopped_max_iterations`.

`MAX_ITERATIONS` (default 10) makes an infinite loop impossible regardless of what the model says.

### Tools

Every tool (`agent/tools/base.py`) declares a `name`, `description`, a Pydantic `input_model`
(used both to validate input and to generate the JSON schema shown to the model), and an
`_execute` method returning a `ToolResult(success, output, error)`. Tool exceptions are always
caught — a broken tool can never crash the loop.

Built in:

| Tool | Purpose | Notes |
|---|---|---|
| `calculator` | Arithmetic | Parses an AST and whitelists operators — never calls `eval()`. |
| `read_file` | Read a text file | Sandboxed to `WORKSPACE_DIR`; rejects path traversal. |
| `write_file` | Write a text file | Sandboxed to `WORKSPACE_DIR`; filename may not contain path separators. |
| `web_search` | Web search | Disabled and returns a clear error unless `SEARCH_API_KEY` (Brave Search) is set. Never fabricates results. |

#### Adding a new tool

1. Create `agent/tools/your_tool.py` with a Pydantic `YourToolInput(BaseModel)` and a class
   `YourTool(Tool)` implementing `_execute(self, parsed_input) -> ToolResult`.
2. Register it in `agent.tools.build_default_registry` (or wherever you construct the registry).

That's it — the model automatically sees its name/description/schema via
`ToolRegistry.describe_all()`, and input validation is handled by the base class.

## Installation

```bash
cd ai-agent-loop
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt        # or requirements-dev.txt to also run tests/lint
```

## Configuration

Copy `.env.example` to `.env` and fill in your key:

```bash
cp .env.example .env
```

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | — | Get one at https://console.anthropic.com/settings/keys |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-5-20250929` | Model ID |
| `MAX_ITERATIONS` | No | `10` | Hard cap on loop iterations |
| `WORKSPACE_DIR` | No | `./workspace` | Sandbox for file tools |
| `RUNS_DIR` | No | `./runs` | Where run logs are written |
| `SEARCH_API_KEY` | No | unset | Brave Search API key; enables `web_search` |
| `REQUEST_TIMEOUT_SECONDS` | No | `60` | Per-request Anthropic API timeout |

If `ANTHROPIC_API_KEY` is missing, the program exits immediately with a clear message — it never
crashes with a raw traceback, and it never logs secret values.

## Running the agent

```bash
python main.py "Calculate the total cost of buying 17 items at $23.50 each and then adding 8.25% tax. Save the result to a text file."
python main.py --max-iterations 5 "Summarize the contents of notes.txt in the workspace"
python main.py                       # interactive: prompts for a goal
```

Example trace (abridged):

```
[Iteration 1/10]

Action: TOOL
  Compute the subtotal for 17 items at $23.50 each.
  Tool: calculator({'expression': '17 * 23.50'})

Observation (ok): {'expression': '17 * 23.50', 'result': 399.5}

Evaluation:
  Progress: 40%
  Confidence: 0.45
  Next step: apply 8.25% tax to the subtotal

Decision: Continue -- apply 8.25% tax to the subtotal
```

## Run history

Each run writes to `runs/`:

- `runs/<run_id>.events.jsonl` — one JSON line per event (plan, action, observation, evaluation,
  replan), appended live as the run progresses, so a crash mid-run still leaves a trail.
- `runs/<run_id>.json` — the full final state snapshot (goal, criteria, plan, every action /
  observation / evaluation, findings, errors, final answer, status).

`runs/` is gitignored — nothing there is committed.

## Tests

No network calls — the Anthropic SDK is either mocked directly (`tests/test_llm_client.py`) or
swapped for a scripted `FakeLLMClient` (`tests/conftest.py`) that drives the real orchestrator,
state, and tool code.

```bash
pip install -r requirements-dev.txt
pytest -q
ruff check .
black --check .
```

Covers: state init/mutation, tool registration/execution/failure, path-traversal protection,
malformed-LLM-output recovery, stopping on success, stopping at max iterations, duplicate-action
detection and forced replanning, replanning updating the plan, a model-proposed `FINAL` being
accepted vs. rejected by the evaluator, and run persistence.

## Security notes

- The model never gets shell access. Every side effect goes through an explicit, registered tool
  with a validated Pydantic input schema.
- The calculator evaluates via an AST walker with a whitelist of operators — never `eval()`/`exec()`.
- File tools are sandboxed to `WORKSPACE_DIR`; both the read and write paths resolve and verify the
  final path stays inside that directory, and written filenames may not contain path separators.
- `web_search` never fabricates results — if unconfigured, it returns a structured error.
- Secrets (`ANTHROPIC_API_KEY`, `SEARCH_API_KEY`) are read from the environment and are never
  printed, logged, or included in run files.
