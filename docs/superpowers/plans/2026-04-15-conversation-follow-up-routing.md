# Conversation Follow-Up Routing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make short conversational follow-ups like `2`, `killblack`, or `1, 1.2, 1, 8080` resolve against the previous assistant prompt instead of being treated as brand-new requests.

**Architecture:** Keep the first implementation narrow and state-driven. Persist prompt metadata inside `task_snapshot`, interpret short follow-up replies in the request router before graph execution, and rewrite them into explicit natural-language supplements so the existing graph/planner/resolver stack can keep working with minimal churn.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic-compatible request persistence, Pydantic task snapshots, pytest

---

## Chunk 1: Prompt State And Interpreter

### Task 1: Add failing unit tests for follow-up interpretation

**Files:**
- Create: `tests/test_follow_up_interpreter.py`
- Modify: `tests/test_api_requests.py`

- [ ] **Step 1: Write failing tests for ambiguity choice replies**

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/test_follow_up_interpreter.py -k ambiguity`

- [ ] **Step 3: Write failing tests for unlabeled missing-input replies**

- [ ] **Step 4: Run the focused tests and confirm they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/test_follow_up_interpreter.py -k missing_input`

- [ ] **Step 5: Add failing API tests that verify the router passes rewritten follow-up text into graph execution**

- [ ] **Step 6: Run the focused API tests and confirm they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/test_api_requests.py -k follow_up`

## Chunk 2: Runtime Wiring

### Task 2: Persist prompt metadata in task snapshots

**Files:**
- Modify: `src/chatops/schemas/tasks.py`
- Modify: `src/chatops/services/task_snapshot_builder.py`

- [ ] **Step 1: Extend `TaskSnapshot` with an optional `follow_up_prompt` payload**

- [ ] **Step 2: Add builder support so ambiguity and input-required states can include prompt metadata**

- [ ] **Step 3: Run schema-related tests**

Run: `PYTHONPATH=src python3 -m pytest tests/test_graph_service.py -k 'ambiguity or input_required'`

### Task 3: Implement the follow-up interpreter

**Files:**
- Create: `src/chatops/services/follow_up_interpreter.py`
- Test: `tests/test_follow_up_interpreter.py`

- [ ] **Step 1: Implement ambiguity option parsing for numeric, ordinal, letter, and exact-label replies**

- [ ] **Step 2: Implement missing-input positional parsing for single-field and comma-separated replies**

- [ ] **Step 3: Keep rewriting output explicit, e.g. `project_name=killblack` or `<previous message>\\n애플리케이션 생성`**

- [ ] **Step 4: Run the new interpreter tests**

Run: `PYTHONPATH=src python3 -m pytest tests/test_follow_up_interpreter.py`

### Task 4: Integrate router-level follow-up rewriting

**Files:**
- Modify: `src/chatops/api/routers/requests.py`
- Modify: `tests/test_api_requests.py`

- [ ] **Step 1: Pass previous `task_snapshot` into session context**

- [ ] **Step 2: Invoke the interpreter before preview/graph execution for `ambiguous` and `input_required` previous requests**

- [ ] **Step 3: Use the rewritten message for graph preview/execution while preserving the user’s original message for history**

- [ ] **Step 4: Run focused API tests**

Run: `PYTHONPATH=src python3 -m pytest tests/test_api_requests.py -k follow_up`

## Chunk 3: Regression Verification

### Task 5: Verify existing conversational flows still work

**Files:**
- Test: `tests/test_graph_service.py`
- Test: `tests/test_api_requests.py`
- Test: `tests/test_parameter_resolver.py`
- Test: `tests/test_registry_service.py`

- [ ] **Step 1: Run interpreter, API, and graph follow-up tests**

Run: `PYTHONPATH=src python3 -m pytest tests/test_follow_up_interpreter.py tests/test_api_requests.py tests/test_graph_service.py -k 'follow_up or ambiguity or input_required'`

- [ ] **Step 2: Run resolver and registry regression tests**

Run: `PYTHONPATH=src python3 -m pytest tests/test_parameter_resolver.py tests/test_registry_service.py`

- [ ] **Step 3: Review remaining gaps**

Notes:
- Pending-approval numeric replies like `1`/`2` are deferred unless approval prompts are made explicitly choice-based.
- Multi-turn correction editing (`아니 cpu는 2로`) continues to use the existing approval/correction path in this iteration.
