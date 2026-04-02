# Session Message API Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose chat-first session APIs that return session lists and paginated message threads without requiring the frontend to stitch together request resources.

**Architecture:** Keep `RequestRecord` as the execution/audit storage model, but add a message view-model layer that projects each request into synthetic `user` and `assistant` chat messages. Extend the `sessions` router with list/detail/message endpoints and use cursor pagination over the flattened message thread.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, pytest

---

## Chunk 1: Public Session/Message Contracts

### Task 1: Define new session/message schemas

**Files:**
- Create: `src/chatops/schemas/messages.py`
- Modify: `src/chatops/schemas/sessions.py`
- Test: `tests/test_api_sessions.py`

- [ ] **Step 1: Write the failing schema/API contract tests**
- [ ] **Step 2: Run `PYTHONPATH=. pytest -q tests/test_api_sessions.py -k 'session_list or session_detail or session_messages or post_message'` and verify failure**
- [ ] **Step 3: Add message, session list, and session detail schemas with examples**
- [ ] **Step 4: Re-run the targeted tests and verify they still fail only on missing router behavior**

## Chunk 2: Message Projection and Pagination

### Task 2: Build request-to-message projection service

**Files:**
- Create: `src/chatops/services/session_messages.py`
- Modify: `src/chatops/db/repositories.py`
- Test: `tests/test_api_sessions.py`

- [ ] **Step 1: Write failing tests for message flattening and cursor pagination**
- [ ] **Step 2: Run targeted tests and verify failure**
- [ ] **Step 3: Implement request querying helpers and message projection service**
- [ ] **Step 4: Re-run targeted tests and verify projection behavior passes**

## Chunk 3: Session Router Conversion

### Task 3: Add chat-first session endpoints

**Files:**
- Modify: `src/chatops/api/routers/sessions.py`
- Modify: `src/chatops/api/dependencies.py`
- Modify: `tests/test_api_sessions.py`
- Test: `tests/test_api_sessions.py`

- [ ] **Step 1: Write failing API tests for `GET /sessions`, enriched `GET /sessions/{session_id}`, `GET /sessions/{session_id}/messages`, and `POST /sessions/{session_id}/messages`**
- [ ] **Step 2: Run targeted tests and verify failure**
- [ ] **Step 3: Implement the endpoints using the message projection layer and existing graph/request flow**
- [ ] **Step 4: Re-run targeted tests and verify they pass**

## Chunk 4: Regression Verification

### Task 4: Verify existing request APIs still work

**Files:**
- Test: `tests/test_api_requests.py`
- Test: `tests/test_api_sessions.py`

- [ ] **Step 1: Run `PYTHONPATH=. pytest -q tests/test_api_requests.py tests/test_api_sessions.py`**
- [ ] **Step 2: Fix any regressions with minimal code changes**
- [ ] **Step 3: Re-run the same test command and verify all pass**
