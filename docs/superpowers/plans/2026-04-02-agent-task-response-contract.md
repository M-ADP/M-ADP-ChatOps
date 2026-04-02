# Agent Task Response Contract Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persisted structured `task` snapshot to ChatOps backend responses and SSE events while preserving existing natural-language fields.

**Architecture:** Introduce a dedicated task snapshot schema and builder, persist the latest snapshot on each request row, and thread the snapshot through graph results, router responses, and event payloads. Keep the rollout additive so existing clients continue to consume `assistant_message` and `final_response`.

**Tech Stack:** Python, FastAPI, Pydantic v2, SQLAlchemy, pytest

---

## File Map

- Create: `src/chatops/schemas/tasks.py`
- Create: `src/chatops/services/task_snapshot_builder.py`
- Modify: `src/chatops/schemas/requests.py`
- Modify: `src/chatops/graph/service.py`
- Modify: `src/chatops/graph/state.py`
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/api/routers/requests.py`
- Modify: `src/chatops/services/events.py`
- Modify: `src/chatops/db/models.py`
- Modify: `src/chatops/db/repositories.py`
- Modify: `migrations/*` if the repo tracks schema migrations manually
- Test: `tests/test_api_requests.py`
- Test: `tests/test_graph_service.py`
- Test: `tests/test_command_planner.py`
- Test: `tests/test_query_planner.py`

## Chunk 1: Task Snapshot Schema and Builder

### Task 1: Add request-facing task schemas

**Files:**
- Create: `src/chatops/schemas/tasks.py`
- Modify: `src/chatops/schemas/requests.py`
- Test: `tests/test_api_requests.py`

- [ ] **Step 1: Write the failing schema test**

Add assertions in `tests/test_api_requests.py` that `RequestResponse`, `ApproveRequestResponse`, and `RejectRequestResponse` accept a `task` payload and preserve it in `model_dump()`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/test_api_requests.py::test_request_schemas_and_auth_context_match_contract`
Expected: FAIL because the response schemas do not yet expose `task`

- [ ] **Step 3: Write minimal schema implementation**

Create `src/chatops/schemas/tasks.py` with:

- `TaskInputField`
- `TaskSnapshot`

Update `src/chatops/schemas/requests.py` so:

- `RequestResponse.task: TaskSnapshot | None`
- `ApproveRequestResponse.task: TaskSnapshot | None`
- `RejectRequestResponse.task: TaskSnapshot | None`

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/test_api_requests.py::test_request_schemas_and_auth_context_match_contract`
Expected: PASS

### Task 2: Add a centralized task snapshot builder

**Files:**
- Create: `src/chatops/services/task_snapshot_builder.py`
- Test: `tests/test_graph_service.py`

- [ ] **Step 1: Write the failing builder behavior test**

Add a targeted test in `tests/test_graph_service.py` that expects a command request result to expose:

- user-facing task title
- approval state
- target references
- filled and missing inputs
- next actions

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/test_graph_service.py::test_command_request_exposes_task_snapshot`
Expected: FAIL because `GraphResult` has no task snapshot

- [ ] **Step 3: Write minimal builder implementation**

Implement `TaskSnapshotBuilder` with methods to:

- build from operation metadata + resolved inputs + request state
- derive `approval_state`
- derive `next_actions`
- normalize missing input labels

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/test_graph_service.py::test_command_request_exposes_task_snapshot`
Expected: PASS

## Chunk 2: Graph and Persistence Wiring

### Task 3: Add task snapshot to graph state and result

**Files:**
- Modify: `src/chatops/graph/state.py`
- Modify: `src/chatops/graph/service.py`
- Modify: `src/chatops/graph/nodes.py`
- Test: `tests/test_graph_service.py`

- [ ] **Step 1: Write the failing graph result test**

Expand graph tests to assert `GraphResult.task_snapshot` is populated for:

- input required command
- pending approval command
- completed query

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/test_graph_service.py`
Expected: FAIL on the new assertions

- [ ] **Step 3: Write minimal graph wiring**

Update graph state, node transitions, and `GraphResult` so the latest task snapshot is carried alongside `final_response`.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/test_graph_service.py`
Expected: PASS

### Task 4: Persist the latest task snapshot on requests

**Files:**
- Modify: `src/chatops/db/models.py`
- Modify: `src/chatops/db/repositories.py`
- Modify: `src/chatops/api/routers/requests.py`
- Test: `tests/test_api_requests.py`

- [ ] **Step 1: Write the failing API persistence test**

Add API assertions showing that:

- `POST /requests` returns `task`
- `GET /requests/{id}` returns the same `task`
- approval/rejection responses return updated `task`

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/test_api_requests.py`
Expected: FAIL because requests are not persisting or returning `task`

- [ ] **Step 3: Write minimal persistence implementation**

Add `task_snapshot` persistence to the request row and write/read it in request endpoints.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/test_api_requests.py`
Expected: PASS

## Chunk 3: Event Payloads and Final Verification

### Task 5: Add task snapshots to event payloads

**Files:**
- Modify: `src/chatops/services/events.py`
- Modify: `src/chatops/api/routers/requests.py`
- Test: `tests/test_api_requests.py`

- [ ] **Step 1: Write the failing event payload test**

Add assertions that emitted request events contain `task` inside the payload data for:

- create request
- approval required
- completed response

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest -q tests/test_api_requests.py::test_create_request_emits_task_snapshot_in_events`
Expected: FAIL because the event payload does not include `task`

- [ ] **Step 3: Write minimal event payload implementation**

Thread the current task snapshot into all relevant event payload builders.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest -q tests/test_api_requests.py::test_create_request_emits_task_snapshot_in_events`
Expected: PASS

### Task 6: Run targeted regression verification

**Files:**
- Test: `tests/test_command_planner.py`
- Test: `tests/test_query_planner.py`
- Test: `tests/test_graph_service.py`
- Test: `tests/test_api_requests.py`
- Test: `tests/test_api_sessions.py`
- Test: `tests/test_api_health.py`

- [ ] **Step 1: Run planner and graph regression suites**

Run: `PYTHONPATH=. pytest -q tests/test_command_planner.py tests/test_query_planner.py tests/test_graph_service.py`
Expected: PASS

- [ ] **Step 2: Run API regression suites**

Run: `PYTHONPATH=. pytest -q tests/test_api_requests.py tests/test_api_sessions.py tests/test_api_health.py`
Expected: PASS

- [ ] **Step 3: Summarize frontend handoff contract**

Document for the frontend team:

- the new `task` response field
- the `approval_state` meanings
- the event payload contract

