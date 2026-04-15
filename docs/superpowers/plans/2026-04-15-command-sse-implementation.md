# Command SSE Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make command requests request-first and SSE-driven without breaking the frontend's structured event contract.

**Architecture:** Extend the session message response so the frontend can grab `request_id` immediately, route command handling through the existing async worker path, and layer synthetic conversational `response.delta` events ahead of final structured request state events. Approval execution keeps its structured terminal events and now emits `execution.started` plus optional execution narration.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, pytest

---

## Chunk 1: Request Metadata Contract

### Task 1: Expand `POST /messages` response schema

**Files:**
- Modify: `src/chatops/schemas/messages.py`
- Modify: `src/chatops/api/routers/sessions.py`
- Test: `tests/test_api_sessions.py`

- [ ] **Step 1: Write the failing test**

Add a session API test asserting `POST /messages` returns `request_id`, `request_status`, `request_type`, `task`, and preserves `messages`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. /Users/jjm/Desktop/M-ADP-ChatOps/.venv/bin/pytest tests/test_api_sessions.py::test_post_session_message_returns_request_metadata -q`
Expected: FAIL because the schema does not expose request metadata.

- [ ] **Step 3: Write minimal implementation**

Update `CreateSessionMessageResponse` and `post_session_message()` to surface request metadata from the created request.

- [ ] **Step 4: Run test to verify it passes**

Run the same pytest command and confirm PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: return request metadata from session messages`

## Chunk 2: Async Command Creation

### Task 2: Make command requests return before graph completion

**Files:**
- Modify: `src/chatops/api/routers/requests.py`
- Modify: `src/chatops/api/routers/sessions.py`
- Test: `tests/test_api_sessions.py`
- Test: `tests/test_api_requests.py`
- Test: `tests/test_sse_stream.py`

- [ ] **Step 1: Write the failing tests**

Add tests asserting command requests created through `POST /messages` and `POST /requests` return quickly with `status=processing` and persist a request row before SSE resolution.

- [ ] **Step 2: Run tests to verify they fail**

Run targeted pytest selectors for the new async command tests.

- [ ] **Step 3: Write minimal implementation**

Route previewed `command` requests through async worker creation, persist initial request status, and return immediately.

- [ ] **Step 4: Run tests to verify they pass**

Run the new selectors, then the affected request/session API test files.

- [ ] **Step 5: Commit**

Commit message: `feat: create command requests asynchronously`

## Chunk 3: Conversational SSE Overlay

### Task 3: Emit supplemental command deltas before structured state events

**Files:**
- Modify: `src/chatops/api/routers/requests.py`
- Test: `tests/test_sse_stream.py`
- Test: `tests/test_api_requests.py`

- [ ] **Step 1: Write the failing tests**

Add SSE tests for command `response.started` and `response.delta` events appearing before `approval.required`, `request.input_required`, or `response.completed`, with `synthetic` and `source` metadata.

- [ ] **Step 2: Run tests to verify they fail**

Run the new SSE test selectors and confirm the contract is not yet implemented.

- [ ] **Step 3: Write minimal implementation**

Add a helper that chunks `final_response`, emits synthetic deltas only when no real chunks were streamed, and reuses it from the async worker command path.

- [ ] **Step 4: Run tests to verify they pass**

Run the SSE selectors, then `tests/test_sse_stream.py` and `tests/test_api_requests.py`.

- [ ] **Step 5: Commit**

Commit message: `feat: stream conversational command deltas`

## Chunk 4: Approval Execution Start

### Task 4: Emit `execution.started` on approval flows

**Files:**
- Modify: `src/chatops/api/routers/requests.py`
- Test: `tests/test_api_requests.py`

- [ ] **Step 1: Write the failing tests**

Add approval tests covering REST approval and natural-language approval paths, asserting `execution.started` is emitted before terminal execution events.

- [ ] **Step 2: Run tests to verify they fail**

Run targeted approval event selectors and confirm missing start events.

- [ ] **Step 3: Write minimal implementation**

Call the existing helper in both approval entrypoints after the atomic status transition succeeds.

- [ ] **Step 4: Run tests to verify they pass**

Run the targeted selectors and then the full affected request test file.

- [ ] **Step 5: Commit**

Commit message: `feat: emit execution started events`

## Chunk 5: Verification and Delivery

### Task 5: Verify, push, and hand off

**Files:**
- Modify: none

- [ ] **Step 1: Run focused verification**

Run:
- `PYTHONPATH=. /Users/jjm/Desktop/M-ADP-ChatOps/.venv/bin/pytest tests/test_api_sessions.py tests/test_api_requests.py tests/test_sse_stream.py -q`

- [ ] **Step 2: Run broader regression checks**

Run:
- `PYTHONPATH=. /Users/jjm/Desktop/M-ADP-ChatOps/.venv/bin/pytest tests/test_graph_service.py tests/test_follow_up_interpreter.py tests/test_multistep.py -q`

- [ ] **Step 3: Stage and commit**

Use focused commit messages if work landed in multiple chunks and there are staged changes left.

- [ ] **Step 4: Push branch**

Run: `git push -u origin dev-0.1.18`

- [ ] **Step 5: Report evidence**

Summarize exact commands run, passing test counts, commits, and branch push result.
