# ChatOps 80-Point Recovery Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the production audit score from the low-60s to 80+ by fixing the remaining structural weaknesses: narrow evaluation coverage, regex-heavy slot extraction, oversized orchestration modules, contract drift, and incomplete fallback/observability.

**Architecture:** Keep the existing FastAPI + LangGraph flow, but move policy and planning decisions into small services with explicit interfaces. Expand the quality harness first so every later change is measured against realistic scenarios instead of a narrow happy-path seed suite.

**Tech Stack:** Python, FastAPI, LangGraph, Pydantic, SQLAlchemy, pytest

---

## Chunk 1: Expand the Evaluation Gate

### Task 1: Replace the seed-only score with a real audit suite

**Files:**
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/evaluation/harness.py`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_quality_score.py`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/fixtures/quality_scenarios.json`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_quality_scenarios.py`

- [ ] **Step 1: Write the failing scenario-corpus test**

```python
def test_quality_suite_uses_at_least_30_realistic_scenarios() -> None:
    scenarios = load_quality_scenarios()
    assert len(scenarios) >= 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_quality_scenarios.py -q`
Expected: FAIL because the scenario corpus file and loader do not exist yet.

- [ ] **Step 3: Implement the scenario corpus loader and broaden the harness**

Add support for:
- ambiguity assertions
- clarification assertions
- fallback-used assertions
- confirmation-required assertions
- unsupported inquiry assertions
- permission failure assertions

- [ ] **Step 4: Populate at least 30 scenarios**

Include:
- simple queries
- conditional queries
- multi-hop lookup flows
- missing-input queries
- ambiguous queries
- invalid resource names
- downstream 404/403/5xx cases
- destructive commands
- stale approval and correction races
- incomplete downstream payload cases

- [ ] **Step 5: Run the suite**

Run: `python3 -m pytest tests/test_quality_score.py tests/test_quality_scenarios.py -q`
Expected: PASS with the seed suite replaced by a broader gate.

- [ ] **Step 6: Commit**

```bash
git add src/chatops/evaluation/harness.py tests/test_quality_score.py tests/fixtures/quality_scenarios.json tests/test_quality_scenarios.py
git commit -m "test: broaden chatops quality audit scenarios"
```

### Task 2: Tie score bands to the audit criteria

**Files:**
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/evaluation/harness.py`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_quality_metrics.py`

- [ ] **Step 1: Write the failing metric-weight test**

```python
def test_quality_report_includes_production_audit_bands() -> None:
    report = build_example_report()
    assert "maintainability" in report.metric_scores
    assert "extensibility" in report.metric_scores
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_quality_metrics.py -q`
Expected: FAIL because the current harness does not score those bands.

- [ ] **Step 3: Implement weighted metric bands**

Add explicit scoring for:
- intent accuracy
- slot accuracy
- workflow correctness
- clarification behavior
- safety behavior
- maintainability proxies
- extensibility proxies

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_quality_metrics.py tests/test_quality_score.py tests/test_quality_scenarios.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chatops/evaluation/harness.py tests/test_quality_metrics.py tests/test_quality_score.py tests/test_quality_scenarios.py
git commit -m "test: score chatops quality using production audit bands"
```

## Chunk 2: Replace Regex-Only Extraction with Typed Slot Extractors

### Task 3: Introduce typed slot models per operation family

**Files:**
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/services/slots.py`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/services/resolver.py`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_slot_models.py`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_parameter_resolver.py`

- [ ] **Step 1: Write the failing slot-model test**

```python
def test_project_create_slots_validate_numeric_ranges() -> None:
    slots = ProjectCreateSlots.model_validate({"name": "demo", "max_cpu": 0, "max_memory": 0.5, "max_disk": 10})
    assert slots.max_cpu == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_slot_models.py -q`
Expected: FAIL because `slots.py` does not exist.

- [ ] **Step 3: Implement slot models**

Create models for:
- `ProjectCreateSlots`
- `ProjectRenameSlots`
- `MemberMutationSlots`
- `ApplicationCreateSlots`
- `ApplicationGithubSlots`
- `MonitoringTrafficSlots`

Use Pydantic validators for:
- blank strings
- numeric ranges
- required field combinations
- structured time windows

- [ ] **Step 4: Refactor resolver to return typed data first**

Keep regex extraction as a fallback only. Resolve to a typed slot object, then dump into the existing `resolved_inputs` structure.

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_slot_models.py tests/test_parameter_resolver.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chatops/services/slots.py src/chatops/services/resolver.py tests/test_slot_models.py tests/test_parameter_resolver.py
git commit -m "refactor: add typed slot extraction models"
```

## Chunk 3: Break the Orchestrator into Smaller Units

### Task 4: Split query, command, and precheck orchestration out of `nodes.py`

**Files:**
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/graph/nodes.py`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/graph/command_planner.py`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/graph/precheck_service.py`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/graph/query_planner.py`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_command_planner.py`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_precheck_service.py`

- [ ] **Step 1: Write the failing extraction boundary tests**

```python
def test_command_planner_returns_pending_approval_for_complete_medium_risk_command() -> None:
    ...

def test_precheck_service_returns_resolved_ids_without_graph_state_mutation() -> None:
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_command_planner.py tests/test_precheck_service.py -q`
Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement the split**

Move:
- query selection and clarification into `query_planner.py`
- command planning and plan text generation into `command_planner.py`
- auth/resource precheck into `precheck_service.py`

Keep `WorkflowNodes` as a thin composition layer only.

- [ ] **Step 4: Enforce file-size reduction**

Target:
- `nodes.py` under 500 lines
- no business-policy helper blocks left inside `WorkflowNodes`

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_command_planner.py tests/test_precheck_service.py tests/test_graph_service.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/chatops/graph/nodes.py src/chatops/graph/command_planner.py src/chatops/graph/precheck_service.py src/chatops/graph/query_planner.py tests/test_command_planner.py tests/test_precheck_service.py tests/test_graph_service.py
git commit -m "refactor: split orchestration policies out of workflow nodes"
```

## Chunk 4: Eliminate Contract Drift and Standardize Fallback Behavior

### Task 5: Align OpenAPI, registry metadata, and fallback policy

**Files:**
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/apis/application.yaml`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/apis/project.yaml`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/apis/monitoring.yaml`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/ai_registry/monitoring.get_app_deployment_traffic.ai.yaml`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_openapi_contracts.py`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/services/downstream_dispatcher.py`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_fallback_matrix.py`

- [ ] **Step 1: Write the failing contract test**

```python
def test_application_and_project_specs_both_expose_required_user_headers() -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_openapi_contracts.py -q`
Expected: FAIL because `application.yaml` does not currently mirror the header contract seen in `project.yaml`.

- [ ] **Step 3: Fix the spec drift**

Standardize:
- `X-User-Id`
- `X-User-Role`
- response envelope conventions for success and error payloads

- [ ] **Step 4: Write the failing fallback matrix test**

```python
def test_not_found_errors_try_supported_fallback_before_failing() -> None:
    ...
```

- [ ] **Step 5: Implement a fallback matrix**

For each operation family, define:
- primary lookup
- allowed fallback lookups
- user-facing clarification when all fallbacks fail

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/test_openapi_contracts.py tests/test_fallback_matrix.py tests/test_downstream_dispatch.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add apis/application.yaml apis/project.yaml apis/monitoring.yaml ai_registry/monitoring.get_app_deployment_traffic.ai.yaml src/chatops/services/downstream_dispatcher.py tests/test_openapi_contracts.py tests/test_fallback_matrix.py tests/test_downstream_dispatch.py
git commit -m "fix: align api contracts and standardize fallback matrix"
```

## Chunk 5: Add Observability That Can Support a Real Audit

### Task 6: Emit structured audit logs and fallback markers everywhere

**Files:**
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/graph/nodes.py`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/services/events.py`
- Create: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_observability.py`

- [ ] **Step 1: Write the failing observability test**

```python
def test_downstream_execution_logs_include_fallback_and_request_context() -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_observability.py -q`
Expected: FAIL because fallback usage and normalized audit context are not asserted end-to-end yet.

- [ ] **Step 3: Implement structured audit events**

Every query/command execution log should include:
- `request_id`
- `session_id`
- `user_id`
- `operation`
- `latency_ms`
- `downstream`
- `status_code`
- `fallback_used`
- `clarification_type`

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_observability.py tests/test_graph_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/chatops/graph/nodes.py src/chatops/services/events.py tests/test_observability.py tests/test_graph_service.py
git commit -m "feat: add structured chatops audit observability"
```

## Expected Score Movement

- After Chunk 1: score credibility improves, but production score likely remains around 63-66 because the code is only better measured.
- After Chunk 2: parameter extraction and missing-input handling can realistically move from 6 to 8.
- After Chunk 3: maintainability can move from 4 to 7 if `nodes.py` is reduced and policies are isolated.
- After Chunk 4: API selection, exception handling, and extensibility can move from the mid-6s to the high-7s.
- After Chunk 5: observability closes the audit gap that still blocks a credible 80+ claim.

## Definition of Done for an 80+ Re-score

- At least 30 realistic audit scenarios exist and run in CI.
- `nodes.py` is under 500 lines.
- Resolver is typed-first, not regex-first.
- OpenAPI and registry contracts are aligned across project, app, and monitoring domains.
- Fallback behavior is standardized and tested.
- Structured audit logs exist for every downstream execution path.
- A fresh audit re-score lands at 80 or above without excluding maintainability or extensibility.

