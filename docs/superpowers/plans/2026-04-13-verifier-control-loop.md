# Verifier Control Loop Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make post-execution control flow verifier-led so query and command requests transition through `success`, `retry`, `clarify`, `escalate`, and `stop` based on verifier decisions instead of raw downstream result shortcuts.

**Architecture:** Keep the existing planner, specialist, approval, and persistence flow intact, but replace the fixed `verify -> interpret/respond` edges with explicit verifier routing. After each execution, normalize `verifier_decision + policy_decision` into a single route, loop back into execution only for allowed retries, and finalize `clarify/escalate/stop` with dedicated state builders so `task_snapshot`, request status, and API responses all reflect verifier authority.

**Tech Stack:** Python, LangGraph, FastAPI, pytest, Bedrock-backed LLM service

---

## Current Gaps

- `src/chatops/graph/workflow.py` always routes `verify_query -> interpret_result` and `verify_command -> respond_command`, so verifier output does not actually control the graph.
- `src/chatops/graph/nodes.py` stores `verifier_decision`, but `interpret_result` and `respond_command` still decide terminal status from raw downstream payloads.
- `retry_count` is only advanced in the command path, and neither query nor command has a real retry edge back into execution.
- `TaskSnapshotBuilder` and `RequestStatus` do not yet represent an explicit verifier escalation outcome.

## Chunk 1: Lock The Broken Behavior With Tests

### Task 1: Add graph-level regression tests for verifier-controlled branching

**Files:**
- Create: `tests/test_verifier_control_loop.py`
- Modify: `tests/test_graph_service.py`
- Test: `tests/test_graph_verifier.py`

- [ ] **Step 1: Write a failing command retry test**

```python
def test_command_retry_reenters_execute_and_completes_on_second_attempt() -> None:
    dispatcher = SequencedDispatcher(
        command_results=[
            {"success": False, "summary": "일시적 오류", "status_code": 503},
            {"success": True, "summary": "재시도 후 성공", "status_code": 200},
        ]
    )
    graph_service = build_graph_service(dispatcher=dispatcher, verifier=RetryVerifierLLM())

    pending = graph_service.handle_request(...)
    result = graph_service.resume_request(..., request_id=pending.request_id, approval_granted=True)

    assert dispatcher.command_calls == 2
    assert result.status == "completed"
    assert result.verifier_decision["decision"] == "success"
```

- [ ] **Step 2: Write failing clarify and escalate tests for both query and command**

```python
def test_query_clarify_stops_before_interpretation() -> None:
    llm = SpyLLM(verifier_decision={"decision": "clarify", "summary": "프로젝트 이름이 더 필요합니다."})
    result = build_graph_service(llm_service=llm).handle_request(...)

    assert result.status == "input_required"
    assert result.final_response == "프로젝트 이름이 더 필요합니다."
    assert llm.interpret_calls == 0
```

- [ ] **Step 3: Run targeted tests and confirm they fail against the current fixed-edge workflow**

Run: `PYTHONPATH=. pytest -q tests/test_verifier_control_loop.py tests/test_graph_verifier.py`

Expected: FAIL because `verify_*` nodes do not branch on verifier decisions.

- [ ] **Step 4: Extend `tests/test_graph_service.py` coverage for persisted graph result fields**

```python
assert result.status == "escalated"
assert result.task_snapshot["status"] == "escalated"
assert result.verifier_decision["follow_up_action"] == "human_review"
```

- [ ] **Step 5: Re-run the same test command after implementation and verify the regression suite passes**

Run: `PYTHONPATH=. pytest -q tests/test_verifier_control_loop.py tests/test_graph_service.py tests/test_graph_verifier.py`

Expected: PASS

## Chunk 2: Make Verifier Decisions Drive The Graph

### Task 2: Introduce a normalized verifier transition layer

**Files:**
- Create: `src/chatops/graph/verifier_transition_service.py`
- Create: `tests/test_verifier_transition_service.py`
- Modify: `src/chatops/graph/state.py`
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/graph/workflow.py`

- [ ] **Step 1: Write failing unit tests for route normalization**

```python
def test_transition_service_maps_retry_with_budget_to_retry_route() -> None:
    route = VerifierTransitionService().route(
        verifier_decision={"decision": "retry"},
        policy_decision={"allow_retry": True},
    )
    assert route == "retry"
```

- [ ] **Step 2: Run the new transition-service tests and verify failure**

Run: `PYTHONPATH=. pytest -q tests/test_verifier_transition_service.py`

Expected: FAIL with import or missing implementation errors.

- [ ] **Step 3: Implement a single route normalizer used by both query and command verification**

```python
class VerifierTransitionService:
    def route(self, *, verifier_decision: dict[str, object], policy_decision: dict[str, object]) -> str:
        decision = str(verifier_decision.get("decision", "stop"))
        if decision == "retry" and bool(policy_decision.get("allow_retry", False)):
            return "retry"
        if decision == "success":
            return "success"
        if decision == "clarify":
            return "clarify"
        if decision == "escalate":
            return "escalate"
        return "stop"
```

- [ ] **Step 4: Store the normalized route in graph state**

```python
class GraphState(TypedDict, total=False):
    verifier_route: str | None
```

- [ ] **Step 5: Replace fixed workflow edges with verifier-driven conditional edges**

```python
graph.add_conditional_edges(
    "verify_command",
    lambda state: state["verifier_route"],
    {
        "retry": "execute_command",
        "success": "respond_command",
        "clarify": "finalize_command_verifier_outcome",
        "escalate": "finalize_command_verifier_outcome",
        "stop": "finalize_command_verifier_outcome",
    },
)
```

- [ ] **Step 6: Re-run the transition-service tests and confirm the route mapping passes**

Run: `PYTHONPATH=. pytest -q tests/test_verifier_transition_service.py`

Expected: PASS

### Task 3: Finalize verifier outcomes instead of letting raw payloads decide

**Files:**
- Modify: `src/chatops/domain/enums.py`
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/services/task_snapshot_builder.py`
- Modify: `tests/test_verifier_control_loop.py`
- Modify: `tests/test_api_requests.py`

- [ ] **Step 1: Write failing tests for terminal-state mapping**

```python
@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("clarify", "input_required"),
        ("escalate", "escalated"),
        ("stop", "failed"),
    ],
)
def test_verifier_terminal_routes_build_expected_statuses(decision: str, expected_status: str) -> None:
    ...
```

- [ ] **Step 2: Add an explicit escalated request status and keep it terminal**

```python
class RequestStatus(str, Enum):
    ...
    ESCALATED = "escalated"
```

- [ ] **Step 3: Implement dedicated finalizer nodes for non-success verifier outcomes**

```python
def finalize_command_verifier_outcome(self, state: GraphState) -> GraphState:
    decision = state["verifier_decision"]
    route = state["verifier_route"]
    status = {
        "clarify": RequestStatus.INPUT_REQUIRED.value,
        "escalate": RequestStatus.ESCALATED.value,
        "stop": RequestStatus.FAILED.value,
    }[route]
    return self._build_verifier_terminal_state(state, status=status, summary=str(decision.get("summary", "")))
```

- [ ] **Step 4: Increment retry counts symmetrically and preserve resolved inputs across retry loops**

```python
next_retry_count = retry_count + 1 if verifier_route == "retry" else retry_count
```

- [ ] **Step 5: Update `TaskSnapshotBuilder` mappings for `escalated` and verifier-originated `input_required`**

```python
if request_status == "escalated":
    return ["retry"]
```

- [ ] **Step 6: Re-run the targeted graph and API tests and verify terminal-state behavior passes**

Run: `PYTHONPATH=. pytest -q tests/test_verifier_control_loop.py tests/test_graph_service.py tests/test_api_requests.py`

Expected: PASS

## Chunk 3: Regression, Contracts, And Evaluation

### Task 4: Expand runtime contract coverage for retry, clarify, and escalate paths

**Files:**
- Modify: `tests/evals/fixtures/q1_golden_scenarios.json`
- Modify: `tests/evals/test_q1_agent_runtime_eval.py`
- Modify: `tests/test_graph_runtime_contracts.py`

- [ ] **Step 1: Add golden scenarios that exercise verifier retry, clarify, and escalate outcomes**

```json
{
  "name": "command verifier escalate",
  "message_text": "프로젝트 삭제해줘",
  "expectation": {
    "status": "escalated",
    "request_type": "command"
  }
}
```

- [ ] **Step 2: Run the eval-focused tests and confirm any missing contract behavior still fails**

Run: `PYTHONPATH=. pytest -q tests/evals/test_q1_agent_runtime_eval.py tests/test_graph_runtime_contracts.py`

Expected: FAIL until the new statuses and routes are fully propagated.

- [ ] **Step 3: Update runtime contract assertions to treat verifier-led statuses as first-class outputs**

```python
assert response.model_dump()["verifier"]["decision"] in {"success", "retry", "clarify", "escalate", "stop"}
```

- [ ] **Step 4: Re-run the eval-focused command and verify the new verifier paths pass**

Run: `PYTHONPATH=. pytest -q tests/evals/test_q1_agent_runtime_eval.py tests/test_graph_runtime_contracts.py`

Expected: PASS

- [ ] **Step 5: Run the full test suite before claiming completion**

Run: `PYTHONPATH=. pytest -q`

Expected: PASS

## Implementation Notes

- Do not move planner, approval, or specialist responsibilities while fixing this loop. The first objective is to give verifier output real control over post-execution transitions.
- Prefer one shared verifier transition service over duplicating branch logic inside both `verify_query` and `verify_command`.
- Keep `respond_command` and `interpret_result` strictly success-only. If they still inspect raw failure payloads after this change, verifier is not actually in charge.
- Reuse existing persisted fields (`verifier_decision`, `task_snapshot`, `plan_object`) instead of introducing new storage unless a test proves the current shape is insufficient.

Plan complete and saved to `docs/superpowers/plans/2026-04-13-verifier-control-loop.md`. Ready to execute?
