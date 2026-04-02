# ChatOps AI 고도화 Q1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a Q1-grade orchestrator-controlled specialist multi-agent runtime with planner, verifier, policy, memory, and evaluation support while preserving the existing chat-first public API.

**Architecture:** Extend the current LangGraph workflow into a staged runtime that emits structured planner outputs, routes through domain specialists, executes downstream tools under policy control, and requires verifier decisions before completion. Persist the new AI runtime artifacts as request metadata and session memory while keeping existing request/session/message contracts backward compatible.

**Tech Stack:** FastAPI, LangGraph, SQLAlchemy, Pydantic, pytest

---

## Assumptions Pending User Confirmation

- Reuse the current Groq-backed LLM service in Q1, but separate planner, specialist, verifier, and summary methods logically in code.
- Limit specialists to `project`, `application`, and `monitoring`.
- Keep current public `sessions + messages` and `requests` APIs additive-only. No breaking response removals in Q1.
- Introduce new persisted runtime metadata for `plan`, `verifier_decision`, and `session_summary`.
- Use fake downstream tests plus targeted local smoke tests as the Q1 verification baseline.
- Defer session-scoped SSE redesign and keep request-scoped stream behavior for this phase.

## Chunk 1: Runtime Contracts and Persistence

### Task 1: Define planner, verifier, and runtime metadata schemas

**Files:**
- Create: `src/chatops/schemas/runtime.py`
- Modify: `src/chatops/graph/state.py`
- Modify: `src/chatops/graph/service.py`
- Modify: `src/chatops/schemas/requests.py`
- Modify: `src/chatops/schemas/messages.py`
- Test: `tests/test_graph_runtime_contracts.py`

- [ ] **Step 1: Write failing tests for planner, verifier, and runtime metadata serialization**
- [ ] **Step 2: Run `PYTHONPATH=. pytest -q tests/test_graph_runtime_contracts.py` and verify failure**
- [ ] **Step 3: Add runtime schemas for `plan_object`, `verifier_decision`, `specialist_result`, and session summary payloads**
- [ ] **Step 4: Extend graph state and graph result to carry the new runtime fields**
- [ ] **Step 5: Re-run the targeted tests and verify the schema layer passes**

### Task 2: Persist runtime metadata without breaking existing request/message flows

**Files:**
- Modify: `src/chatops/db/models.py`
- Modify: `src/chatops/db/repositories.py`
- Create: `migrations/versions/0009_add_ai_runtime_metadata.py`
- Modify: `src/chatops/api/routers/requests.py`
- Modify: `src/chatops/services/session_messages.py`
- Test: `tests/test_api_requests.py`
- Test: `tests/test_api_sessions.py`
- Test: `tests/test_db_migrations.py`

- [ ] **Step 1: Write failing persistence tests for request-level runtime metadata and session summary storage**
- [ ] **Step 2: Run the targeted migration and repository tests and verify failure**
- [ ] **Step 3: Add new persisted columns or tables for plan/verifier/session summary metadata**
- [ ] **Step 4: Store and reload runtime metadata through request and message projection paths**
- [ ] **Step 5: Re-run the targeted tests and verify backward compatibility**

## Chunk 2: Planner and Specialist Runtime

### Task 3: Introduce planner service and planner node

**Files:**
- Create: `src/chatops/graph/planner_service.py`
- Modify: `src/chatops/services/llm.py`
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/graph/workflow.py`
- Test: `tests/test_graph_planner.py`

- [ ] **Step 1: Write failing tests for planner output on representative query and command inputs**
- [ ] **Step 2: Run `PYTHONPATH=. pytest -q tests/test_graph_planner.py` and verify failure**
- [ ] **Step 3: Implement planner LLM interface and planner service with structured outputs**
- [ ] **Step 4: Insert planner processing into the graph before domain execution**
- [ ] **Step 5: Re-run the targeted tests and verify planner behavior passes**

### Task 4: Extract project, application, and monitoring specialists

**Files:**
- Create: `src/chatops/graph/specialists/base.py`
- Create: `src/chatops/graph/specialists/project.py`
- Create: `src/chatops/graph/specialists/application.py`
- Create: `src/chatops/graph/specialists/monitoring.py`
- Create: `src/chatops/graph/specialist_router.py`
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/services/downstream_dispatcher.py`
- Test: `tests/test_graph_specialists.py`

- [ ] **Step 1: Write failing tests for specialist routing, slot resolution, and tool argument shaping**
- [ ] **Step 2: Run `PYTHONPATH=. pytest -q tests/test_graph_specialists.py` and verify failure**
- [ ] **Step 3: Implement specialist abstractions and router with orchestrator-controlled invocation**
- [ ] **Step 4: Move domain-specific preparation logic out of the monolithic nodes into specialists**
- [ ] **Step 5: Re-run the targeted tests and verify specialist behavior passes**

## Chunk 3: Verifier and Policy Control

### Task 5: Add verifier service and verifier-driven state transitions

**Files:**
- Create: `src/chatops/graph/verifier_service.py`
- Modify: `src/chatops/services/llm.py`
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/graph/workflow.py`
- Test: `tests/test_graph_verifier.py`

- [ ] **Step 1: Write failing tests for verifier decisions across success, retry, clarify, escalate, and stop cases**
- [ ] **Step 2: Run `PYTHONPATH=. pytest -q tests/test_graph_verifier.py` and verify failure**
- [ ] **Step 3: Implement verifier structured output and decision normalization**
- [ ] **Step 4: Require verifier output before final completion for query and command flows**
- [ ] **Step 5: Re-run the targeted tests and verify verifier-controlled transitions pass**

### Task 6: Separate policy evaluation from planner and specialist reasoning

**Files:**
- Create: `src/chatops/graph/policy_service.py`
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/graph/approval_policy.py`
- Test: `tests/test_graph_policy.py`

- [ ] **Step 1: Write failing tests for approval, destructive-action, retry-limit, and superseded-request policy checks**
- [ ] **Step 2: Run `PYTHONPATH=. pytest -q tests/test_graph_policy.py` and verify failure**
- [ ] **Step 3: Implement policy evaluation as a standalone service with normalized decisions**
- [ ] **Step 4: Route planner and verifier outputs through policy gates before execution or completion**
- [ ] **Step 5: Re-run the targeted tests and verify policy enforcement passes**

## Chunk 4: Memory and Session Intelligence

### Task 7: Add session summary and entity memory services

**Files:**
- Create: `src/chatops/services/session_summary_service.py`
- Create: `src/chatops/services/entity_memory_service.py`
- Modify: `src/chatops/api/routers/sessions.py`
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/services/session_messages.py`
- Test: `tests/test_session_memory.py`

- [ ] **Step 1: Write failing tests for session summary refresh and entity recall behavior**
- [ ] **Step 2: Run `PYTHONPATH=. pytest -q tests/test_session_memory.py` and verify failure**
- [ ] **Step 3: Implement session summary persistence and lookup**
- [ ] **Step 4: Implement entity memory extraction and reuse in planner/specialist flows**
- [ ] **Step 5: Re-run the targeted tests and verify memory behavior passes**

## Chunk 5: API Exposure and Evaluation

### Task 8: Expose runtime metadata through request and session APIs

**Files:**
- Modify: `src/chatops/api/routers/requests.py`
- Modify: `src/chatops/api/routers/sessions.py`
- Modify: `src/chatops/schemas/requests.py`
- Modify: `src/chatops/schemas/messages.py`
- Test: `tests/test_api_requests.py`
- Test: `tests/test_api_sessions.py`

- [ ] **Step 1: Write failing API tests for runtime metadata in request and assistant task payloads**
- [ ] **Step 2: Run the targeted API tests and verify failure**
- [ ] **Step 3: Add additive API fields for plan and verifier summaries where appropriate**
- [ ] **Step 4: Keep legacy fields intact and verify old clients still parse responses**
- [ ] **Step 5: Re-run the targeted API tests and verify compatibility**

### Task 9: Build Q1 evaluation harness and golden scenarios

**Files:**
- Create: `tests/evals/test_q1_agent_runtime_eval.py`
- Create: `tests/evals/fixtures/q1_golden_scenarios.json`
- Modify: `tests/conftest.py`
- Optionally Create: `scripts/run_q1_eval.py`

- [ ] **Step 1: Write the initial golden scenarios covering planner, specialist, verifier, and policy paths**
- [ ] **Step 2: Run the eval tests and verify the baseline fails**
- [ ] **Step 3: Implement minimal eval harness support and deterministic stubs**
- [ ] **Step 4: Re-run the eval tests and capture baseline metrics**
- [ ] **Step 5: Document the metrics that define Q1 success**

## Chunk 6: End-to-End Verification

### Task 10: Verify the integrated runtime without breaking current ChatOps behavior

**Files:**
- Test: `tests/test_api_requests.py`
- Test: `tests/test_api_sessions.py`
- Test: `tests/test_db_migrations.py`
- Test: `tests/test_graph_planner.py`
- Test: `tests/test_graph_specialists.py`
- Test: `tests/test_graph_verifier.py`
- Test: `tests/test_graph_policy.py`
- Test: `tests/test_session_memory.py`
- Test: `tests/evals/test_q1_agent_runtime_eval.py`

- [ ] **Step 1: Run the targeted runtime and API suites together**
- [ ] **Step 2: Fix regressions with minimal changes**
- [ ] **Step 3: Re-run the full verification set until green**
- [ ] **Step 4: Smoke test `POST /sessions/{id}/messages`, `GET /sessions/{id}`, and approval flows locally**
- [ ] **Step 5: Summarize metric deltas and residual risks before handoff**
