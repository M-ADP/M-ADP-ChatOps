# Decision Trace Logging Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add structured server-side decision trace logs for request routing and node branching without changing user-facing APIs or SSE contracts.

**Architecture:** Introduce one reusable trace logging helper that emits normalized JSON payloads, then call it from the key branch points that decide how a request flows through ChatOps. Keep the scope to server logs only and avoid new persistence or response fields.

**Tech Stack:** Python, FastAPI, logging, pytest

---

## Chunk 1: Trace Helper

### Task 1: Add a reusable decision trace logger

**Files:**
- Create: `src/chatops/services/decision_trace.py`
- Test: `tests/test_decision_trace.py`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run test to verify it fails**
  Run: `PYTHONPATH=. /Users/jjm/Desktop/M-ADP-ChatOps/.venv/bin/pytest tests/test_decision_trace.py -q`
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run test to verify it passes**
- [ ] **Step 5: Commit**

## Chunk 2: Early Routing Trace

### Task 2: Log router, follow-up rewrite, and preview decisions

**Files:**
- Modify: `src/chatops/services/conversation_router.py`
- Modify: `src/chatops/services/follow_up_interpreter.py`
- Modify: `src/chatops/graph/service.py`
- Modify: `src/chatops/api/routers/requests.py`
- Test: `tests/test_api_requests.py`

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run tests to verify they fail**
  Run: `PYTHONPATH=. /Users/jjm/Desktop/M-ADP-ChatOps/.venv/bin/pytest tests/test_api_requests.py::test_create_request_logs_small_talk_route_trace tests/test_api_requests.py::test_create_request_logs_follow_up_rewrite_trace -q`
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

## Chunk 3: Planner and Verifier Trace

### Task 3: Log planner and verifier branching

**Files:**
- Modify: `src/chatops/graph/command_planner.py`
- Modify: `src/chatops/graph/verifier_service.py`
- Test: `tests/test_observability.py`

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run tests to verify they fail**
  Run: `PYTHONPATH=. /Users/jjm/Desktop/M-ADP-ChatOps/.venv/bin/pytest tests/test_observability.py::test_command_planner_logs_missing_input_trace tests/test_observability.py::test_verifier_logs_decision_trace -q`
- [ ] **Step 3: Write minimal implementation**
- [ ] **Step 4: Run tests to verify they pass**
- [ ] **Step 5: Commit**

## Chunk 4: Verification

### Task 4: Run regression checks

**Files:**
- Modify: none

- [ ] **Step 1: Run focused verification**
  Run: `PYTHONPATH=. /Users/jjm/Desktop/M-ADP-ChatOps/.venv/bin/pytest tests/test_decision_trace.py tests/test_api_requests.py tests/test_observability.py -q`
- [ ] **Step 2: Run adjacent regression checks**
  Run: `PYTHONPATH=. /Users/jjm/Desktop/M-ADP-ChatOps/.venv/bin/pytest tests/test_api_sessions.py tests/test_sse_stream.py tests/test_graph_service.py tests/test_follow_up_interpreter.py tests/test_multistep.py -q`
- [ ] **Step 3: Stage and commit**
- [ ] **Step 4: Report evidence**
