# Agent Task Response Contract Design

**Date:** 2026-04-02
**Scope:** ChatOps backend only
**Frontend ownership:** Separate team consumes the contract defined here

---

## Goal

Preserve the current chat-thread UI while changing backend responses from assistant-message-centric payloads to task-centric payloads that support an evolving agent card.

The backend must continue to return existing natural-language fields for backward compatibility, but the primary machine-readable contract becomes a structured `task` snapshot.

## Product Direction

The approved interaction model is `Chat Thread + Evolving Agent Card`.

- The user still types natural-language requests in a chat thread.
- The backend no longer treats the assistant bubble as the primary UI primitive.
- Each request returns a structured task snapshot that the frontend can render as a live operation card.
- Natural-language narration remains available as a short helper string, not as the main state carrier.

## Non-Goals

- No frontend implementation in this repo
- No layout or style changes
- No multi-step autonomous planner that chains several downstream operations automatically
- No breaking removal of `assistant_message` or `final_response`

## Contract Shape

All request-oriented responses should expose an optional `task` object in addition to existing fields.

```json
{
  "request_id": 2001,
  "session_id": 1001,
  "status": "pending_approval",
  "message": "demo 프로젝트에 api 앱 만들어줘",
  "assistant_message": "리소스 값만 채우면 실행 계획으로 넘길 수 있습니다.",
  "task": {
    "kind": "operation",
    "title": "애플리케이션 생성",
    "operation_id": "application.create_apps",
    "status": "pending_approval",
    "request_type": "command",
    "approval_state": "awaiting_approval",
    "risk_level": "medium",
    "target": {
      "project_name": "demo",
      "application_name": "api"
    },
    "filled_inputs": {
      "project_name": "demo",
      "application_name": "api"
    },
    "missing_inputs": [
      { "key": "cpu", "label": "CPU" },
      { "key": "memory", "label": "메모리" },
      { "key": "disk", "label": "디스크" }
    ],
    "next_actions": ["approve", "edit", "cancel"],
    "summary": "demo 프로젝트에 api 앱을 생성하는 작업입니다."
  }
}
```

## Task Snapshot Fields

The task snapshot should be rich enough for the frontend to render a single evolving card without parsing natural-language strings.

### Required fields

- `kind`: currently always `operation`
- `title`: user-facing task name
- `status`: mirrors request status
- `request_type`: `inquiry`, `query`, or `command`
- `approval_state`: derived state for UI buttons and badges
- `next_actions`: UI action hints

### Optional fields

- `operation_id`
- `risk_level`
- `target`
- `filled_inputs`
- `missing_inputs`
- `summary`
- `clarification_type`
- `is_ambiguous`

## Status Mapping

The backend keeps existing request statuses and derives a smaller UI-oriented approval state.

- `input_required` -> `not_ready`
- `ambiguous` -> `needs_clarification`
- `pending_approval` -> `awaiting_approval`
- `executing` -> `approved`
- `completed` -> `completed`
- `failed` -> `failed`
- `rejected` -> `cancelled`
- `approval_expired` -> `expired`

## Query vs Command Behavior

### Query requests

Query requests produce a task snapshot that emphasizes context and result framing.

- `title` should reflect the query operation
- `target` should contain the resolved entity names where available
- `filled_inputs` should contain request filters such as date range
- `next_actions` should expose follow-up analysis affordances such as compare, refine, export

### Command requests

Command requests produce a task snapshot that behaves like a live operation card.

- `missing_inputs` drives inline field UI
- `risk_level` drives approval emphasis
- `approval_state` drives action bar rendering
- `next_actions` changes as status changes

## Persistence Strategy

The `task` snapshot must survive `GET /requests/{id}` and post-approval fetches, not just the original create response.

Because the current request table does not persist enough structured state for reliable reconstruction, the backend will add a persisted `task_snapshot` JSON field on `RequestRecord`.

This field will:

- store the latest machine-readable task snapshot
- be updated whenever request state transitions
- avoid forcing the frontend to reverse-engineer state from `final_response`

## Event Streaming Strategy

SSE events must carry the same task snapshot shape under the payload so the frontend can update an existing agent card in place.

Key event types:

- `request.created`
- `request.input_required`
- `request.ambiguous`
- `approval.required`
- `execution.started`
- `execution.completed`
- `execution.failed`
- `approval.rejected`
- `approval.superseded`

Each event payload should include:

- `type`
- `request_id`
- `session_id`
- `status`
- `final_response`
- `task`

## Backward Compatibility

The rollout should be additive.

- Keep `assistant_message`
- Keep `final_response`
- Keep `missing_inputs`
- Add `task`
- Add task snapshot to event payloads

Existing clients should continue to work unchanged. New clients can switch to the structured contract immediately.

## Backend Components

The cleanest design is to introduce a dedicated task snapshot builder service rather than spreading UI-shaping logic across routers.

### New responsibility

`TaskSnapshotBuilder`

- converts `GraphResult` into a task snapshot for immediate responses
- converts persisted request rows into a task snapshot for fetch endpoints
- normalizes missing input labels
- derives approval state and next actions

### Existing components to extend

- `GraphResult` should expose `task_snapshot`
- `RequestResponse`, `ApproveRequestResponse`, and `RejectRequestResponse` should expose `task`
- request persistence should store `task_snapshot`
- event appenders should include `task`

## Testing Strategy

The change must be driven by tests first.

- schema tests for new response fields
- API tests for `create`, `get`, `approve`, and `reject` responses including `task`
- graph tests for generated `task_snapshot`
- event tests for SSE payload contents

## Risks

### Risk: duplicated state logic

If task shaping is done in routers, graph nodes, and tests independently, the contract will drift.

Mitigation: centralize task shaping in one builder service.

### Risk: partial persistence

If only live responses contain `task`, frontend reload flows will be inconsistent.

Mitigation: persist the current task snapshot on the request record.

### Risk: overfitting frontend details

The backend should not encode presentation layout decisions.

Mitigation: expose semantic state and action hints only, not component names or CSS-oriented structure.

