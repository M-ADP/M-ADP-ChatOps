# ChatOps Request SSE Contract

프론트엔드가 ChatOps 요청 스트림을 그대로 구현할 수 있도록, 현재 백엔드 구현 기준 SSE 계약을 정리한다.

- 기준 일자: 2026-04-15
- 기준 구현:
  - `src/chatops/api/routers/stream.py`
  - `src/chatops/api/routers/requests.py`
  - `src/chatops/services/events.py`
  - `src/chatops/services/task_snapshot_builder.py`
  - `tests/test_sse_stream.py`
  - `tests/test_api_requests.py`
- 이 문서는 과거 설계 문서보다 우선한다. 과거 스펙에 있는 이벤트 중 일부는 현재 구현에서 실제로 emit되지 않는다.

## 1. 스트림 엔드포인트

요청 단위로만 SSE를 연다.

- `GET /chatops/sessions/{session_id}/requests/{request_id}/stream`
- Query
  - `follow=false` 기본값. 현재까지 저장된 이벤트만 재생하고 연결을 닫는다.
  - `follow=true` 이미 저장된 이벤트를 재생한 뒤, 새 이벤트를 기다리며 연결을 유지한다.
- Header
  - `Last-Event-ID`: 마지막으로 받은 `sequence`. 이 값보다 큰 이벤트만 다시 보낸다.

응답 `Content-Type`:

```text
text/event-stream
```

SSE 프레임 형식:

```text
id: 7
event: response.completed
data: {"type":"response.completed","phase":"response",...}

```

중요 규칙:

- `id`는 요청 내부에서 단조 증가하는 `sequence`다.
- `event`는 `request_events.event_type` 값 그대로다.
- `data`는 JSON 문자열 1줄이다.
- 클라이언트는 `sequence` 기준으로 중복 제거하면 된다.

## 2. 재연결과 keep-alive

백엔드는 SSE를 메모리 큐가 아니라 DB 기반으로 재생한다.

- 모든 이벤트는 `request_events` 테이블에 저장된 뒤 스트림으로 나간다.
- `follow=true`일 때 서버는 약 100ms 간격으로 새 이벤트를 폴링한다.
- 새 이벤트가 없고 요청이 아직 terminal이 아니면, 기본 15초마다 keep-alive를 보낸다.

keep-alive 프레임:

```text
: keep-alive

```

프론트 구현 규칙:

- 연결이 끊기면 마지막 `sequence`를 저장해 두고 `Last-Event-ID`로 재연결한다.
- keep-alive는 무시한다.
- `follow=false`는 히스토리 재생용, `follow=true`는 라이브 UX용으로 쓰면 된다.

## 3. 스트림 종료 조건

`follow=true` 스트림은 request 상태가 terminal이면 자동으로 닫힌다.

현재 terminal status:

- `executed`
- `completed`
- `failed`
- `escalated`
- `cancelled`
- `rejected`
- `approval_expired`
- `superseded`

주의:

- terminal status가 되었더라도 마지막 이벤트를 이미 전송했다면 그 뒤 바로 연결이 닫힌다.
- `approval_expired`는 terminal status이지만, 현재 라우터는 별도 `approval.expired` SSE 이벤트를 emit하지 않는다.

## 4. 이벤트 분류

현재 실제로 나가는 SSE 이벤트는 아래와 같다.

### 4.1 구조화 이벤트

아래 이벤트들은 공통적으로 구조화된 payload를 가진다.

- `request.created`
- `context.hydrated`
- `parsing.completed`
- `approval.required`
- `request.ambiguous`
- `request.input_required`
- `response.started`
- `response.completed`
- `request.failed`
- `execution.completed`
- `execution.failed`

공통 필드:

```json
{
  "type": "response.completed",
  "phase": "response",
  "step": "completed",
  "message": "응답 생성을 마쳤습니다.",
  "request_id": 2001,
  "session_id": 1001,
  "status": "completed",
  "progress": 100
}
```

필드 의미:

- `type`: 이벤트 이름과 동일
- `phase`: 프론트 상위 단계 구분용
  - `request`
  - `planning`
  - `approval`
  - `response`
  - `execution`
- `step`: phase 내부 세부 단계
- `message`: 토스트/서브카피/타임라인 문구로 바로 써도 되는 한국어 메시지
- `status`: request 현재 상태
- `progress`: 0~100 정수. 정밀한 진행률이 아니라 UX 단계 표현용

### 4.2 감사 메타데이터가 붙는 이벤트

일부 이벤트에는 아래 감사 필드가 추가될 수 있다.

```json
{
  "user_id": "user-1",
  "operation": "application.get_apps_logs",
  "latency_ms": 12.34,
  "downstream": "application",
  "status_code": 404,
  "fallback_used": true,
  "clarification_type": null
}
```

현재 이 메타데이터가 붙는 이벤트:

- `parsing.completed`
- `approval.required`
- `request.ambiguous`
- `request.input_required`
- `response.completed`
- `request.failed`
- `execution.completed`
- `execution.failed`
- `approval.rejected`

프론트 사용 권장:

- `fallback_used`: "정확 매칭 실패 후 유사 항목으로 보정됨" 배지/로그 용도
- `clarification_type`: `ambiguity`, `missing_input` 같은 보조 문맥
- `status_code`, `downstream`, `operation`: 사용자 노출보다 디버그 패널/관측용에 적합

### 4.3 `task` 필드에 대한 규칙

`task`는 nullable이다.

- command 중심 요청에서는 대체로 채워진다
- inquiry/query 스트리밍 초반 이벤트에서는 `null`일 수 있다
- 특히 async inquiry/query 경로의 `request.created`, `context.hydrated`는 `task=null`일 수 있다
- 프론트는 `task`가 없더라도 이벤트 처리에 실패하면 안 된다
- `task`가 오면 기존 카드 state를 merge/update하고, 없으면 현재 카드 state를 유지하는 방식이 안전하다

## 5. 이벤트별 payload 상세

### `request.created`

요청을 접수했음을 의미한다.

추가 필드:

```json
{
  "request_type": "command",
  "task": { "...TaskSnapshot" }
}
```

특징:

- `progress=10`
- `phase=request`
- `task`가 있으면 초기 카드 렌더링에 바로 사용 가능

### `context.hydrated`

세션 문맥, 엔티티 메모리, 이전 요청 trail을 합친 뒤 emit된다.

추가 필드:

```json
{
  "project_context_count": 1,
  "application_context_count": 2,
  "user_context_count": 0,
  "request_trail_count": 3,
  "task": { "...TaskSnapshot" }
}
```

특징:

- `progress=20`
- UX상 숨겨도 되지만, 디버그 타임라인에는 유용하다

### `parsing.completed`

LLM 분류와 operation 선택이 끝난 상태다.

추가 필드:

```json
{
  "request_type": "command",
  "intent": "execute_command",
  "selected_operation_ids": ["project.create"],
  "resolved_references": {
    "project_name": "demo"
  },
  "missing_inputs": ["cpu", "memory"],
  "task": { "...TaskSnapshot" }
}
```

특징:

- `progress=40`
- 프론트에서 디버그 모드가 아니라면 `selected_operation_ids`는 직접 노출하지 않는 편이 안전하다
- 이 이벤트 뒤에는 보통 아래 셋 중 하나가 따라온다
  - `approval.required`
  - `request.ambiguous`
  - `request.input_required`
  - 또는 바로 `response.completed` / `request.failed`

### `approval.required`

명령이 승인 대기에 들어갔음을 의미한다.

추가 필드:

```json
{
  "final_response": "demo 프로젝트에 api 앱을 생성할게요. 실행할까요?",
  "missing_inputs": null,
  "task": { "...TaskSnapshot" }
}
```

특징:

- `progress=80`
- `phase=approval`
- 프론트는 이 이벤트의 `task`를 승인 카드의 진실 소스로 써야 한다

### `request.ambiguous`

후보 operation이 둘 이상이라 추가 선택이 필요하다.

추가 필드:

```json
{
  "final_response": "어느 대상을 말씀하시는지 확인이 필요합니다.",
  "task": { "...TaskSnapshot" }
}
```

특징:

- `progress=70`
- `task.is_ambiguous`, `task.next_actions`와 함께 해석하면 된다

### `request.input_required`

필수 입력이 비어 추가 입력 폼이 필요하다.

추가 필드:

```json
{
  "final_response": "CPU와 메모리를 알려주세요.",
  "missing_inputs": ["cpu", "memory"],
  "task": { "...TaskSnapshot" }
}
```

특징:

- `progress=70`
- 실제 폼 렌더링은 `task.missing_inputs[].key/label`을 우선 사용하고, 루트 `missing_inputs`는 보조값으로만 쓰는 편이 좋다

### `response.started`

LLM 자유 응답 스트리밍이 시작될 때 1회 emit된다.

추가 필드 없음.

특징:

- `progress=80`
- 현재 `task`, `final_response`, audit 메타데이터가 없다
- inquiry/query의 텍스트 청크가 있을 때만 나온다

### `response.delta`

자유 응답 텍스트 청크다.

payload:

```json
{
  "type": "response.delta",
  "request_id": 2001,
  "session_id": 1001,
  "text": "문의 "
}
```

특징:

- `phase`, `step`, `status`, `progress`, `task`가 없다
- 프론트는 `text`를 누적해서 임시 assistant message를 렌더링하면 된다
- 청크 경계는 문장 경계가 아니다

### `response.completed`

응답 생성이 끝났다.

추가 필드:

```json
{
  "final_response": "배포 방법은 ...",
  "task": { "...TaskSnapshot" }
}
```

특징:

- `progress=100`
- inquiry/query 완료의 최종 정산 이벤트다
- `response.delta`를 누적한 텍스트가 있더라도, 최종 텍스트는 `final_response`로 덮어쓰는 편이 안전하다

### `request.failed`

요청 실패다.

변형 A: 일반 실패 경로

```json
{
  "type": "request.failed",
  "phase": "response",
  "step": "failed",
  "message": "요청 처리에 실패했습니다.",
  "request_id": 2001,
  "session_id": 1001,
  "status": "failed",
  "progress": 100,
  "final_response": "실패 안내 문구",
  "task": { "...TaskSnapshot" }
}
```

변형 B: async worker 예외 fallback 경로

```json
{
  "type": "request.failed",
  "phase": "response",
  "step": "failed",
  "message": "요청 처리에 실패했습니다.",
  "request_id": 2001,
  "session_id": 1001,
  "status": "failed",
  "progress": 100,
  "final_response": "요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
}
```

특징:

- fallback 경로에서는 `task`와 audit 필드가 없을 수 있다
- 프론트는 `final_response`가 있으면 그대로 사용자 메시지로 노출하면 된다

### `execution.completed` / `execution.failed`

승인 후 resume 결과가 끝난 상태다.

추가 필드:

```json
{
  "final_response": "프로젝트를 생성했습니다.",
  "task": { "...TaskSnapshot" }
}
```

특징:

- `phase=execution`
- `progress=100`
- 승인 후 별도 중간 진행 이벤트 없이 바로 terminal 이벤트만 오는 것이 현재 구현이다

### `approval.rejected`

승인 대기 요청이 거절됐다.

payload:

```json
{
  "type": "approval.rejected",
  "request_id": 2001,
  "session_id": 1001,
  "status": "rejected",
  "task": { "...TaskSnapshot" },
  "user_id": "user-1",
  "operation": "project.create",
  "latency_ms": 3.21,
  "downstream": "project",
  "status_code": 200,
  "fallback_used": false,
  "clarification_type": null
}
```

특징:

- 이 이벤트는 구조화 이벤트 형식이 아니다
- `phase`, `step`, `message`, `progress`가 없다
- 거절 UX는 `status=rejected`와 `task.approval_state=cancelled` 기준으로 처리한다

### `approval.superseded`

기존 승인 대기 요청이 사용자의 정정 요청으로 무효화됐다는 의미다.

payload:

```json
{
  "type": "approval.superseded",
  "request_id": 2001,
  "session_id": 1001,
  "status": "superseded",
  "superseded_by": 2002,
  "task": { "...TaskSnapshot" }
}
```

특징:

- 사용자가 "아니, 그게 아니라 ..."처럼 기존 승인 대기 요청을 정정했을 때 이전 요청 스트림에서 발생한다
- 프론트는 기존 카드 액션을 비활성화하고, `superseded_by` 새 요청으로 포커스를 옮기면 된다

## 6. `task` 스냅샷 계약

프론트 UX는 가능하면 텍스트 파싱이 아니라 `task`를 기준으로 동작해야 한다.

현재 `TaskSnapshot` shape:

```json
{
  "kind": "operation",
  "title": "애플리케이션 생성",
  "status": "pending_approval",
  "request_type": "command",
  "approval_state": "awaiting_approval",
  "operation_id": "application.create_apps",
  "risk_level": "medium",
  "target": {
    "project_name": "demo",
    "application_name": "api"
  },
  "filled_inputs": {
    "name": "api",
    "cpu": 1,
    "memory": 512,
    "disk": 10
  },
  "missing_inputs": [
    {
      "key": "cpu",
      "label": "CPU"
    }
  ],
  "next_actions": ["approve", "edit", "cancel"],
  "summary": "demo 프로젝트에 api 앱을 생성하는 승인 대기 작업입니다.",
  "clarification_type": null,
  "is_ambiguous": false
}
```

프론트 해석 권장:

- `title`, `summary`: 카드 제목/서브카피
- `approval_state`: 상태 배지와 CTA 그룹 전환
- `next_actions`: 버튼 렌더링 기준
- `missing_inputs`: 인라인 폼 생성 기준
- `target`, `filled_inputs`: 확인 패널
- `risk_level`: 강조 수준
- `is_ambiguous`, `clarification_type`: 확인형 UX 분기

현재 서버가 만드는 `approval_state`:

- `input_required` -> `not_ready`
- `ambiguous` -> `needs_clarification`
- `pending_approval` -> `awaiting_approval`
- `executing` -> `approved`
- `completed` -> `completed`
- `failed` -> `failed`
- `escalated` -> `failed`
- `rejected` -> `cancelled`
- `approval_expired` -> `expired`

현재 서버가 만드는 `next_actions`:

- `pending_approval` -> `["approve", "edit", "cancel"]`
- `input_required` -> `["fill_inputs", "cancel"]`
- `ambiguous` -> `["choose_option", "cancel"]`
- `executing` -> `["view_progress"]`
- `completed`
  - command -> `["view_result"]`
  - inquiry/query -> `["refine", "compare", "export"]`
- `failed` / `escalated` / `rejected` -> `["retry"]`

## 7. 플로우별 실제 이벤트 순서

### 7.1 inquiry/query + 스트리밍 텍스트

보통 순서는 아래와 같다.

1. `request.created`
2. `context.hydrated`
3. `response.started`
4. `response.delta` x N
5. `parsing.completed`
6. `response.completed`

중요:

- `response.delta`가 `parsing.completed`보다 먼저 올 수 있다
- 프론트는 `parsing.completed`를 기다리지 말고 청크를 바로 렌더링해야 UX가 좋다

### 7.2 command + 승인 대기

1. `request.created`
2. `context.hydrated`
3. `parsing.completed`
4. `approval.required`

이 시점부터 프론트는 승인 카드 UX로 전환한다.

### 7.3 command + 승인 후 완료

현재 실제 SSE는 다음만 보장한다.

1. 기존 스트림에 `execution.completed` 또는 `execution.failed`

중요:

- `execution.started` helper는 코드에 있지만 현재 호출되지 않는다
- 따라서 승인 버튼 클릭 후에는 프론트가 자체 pending UX를 가져야 한다
- 승인 POST 응답과 SSE terminal 이벤트를 함께 처리하면 UX가 가장 안정적이다

### 7.4 command + 거절

1. 기존 스트림에 `approval.rejected`

### 7.5 기존 승인 요청이 정정으로 무효화됨

1. 기존 요청 스트림에 `approval.superseded`
2. 새 요청은 자기 request_id로 별도 스트림 생성

## 8. 프론트 구현 권장사항

### 최소 구현

- `POST /requests`가 202를 반환하면 즉시 `request_id` 기준 `follow=true` SSE를 연다
- 수신한 이벤트를 `sequence` 기준으로 정렬/중복 제거한다
- `response.delta.text`는 누적 렌더링한다
- terminal 이벤트가 오면 최종 상태를 고정한다

### UX 품질을 높이는 구현

- `task`가 있는 이벤트는 모두 같은 카드 state를 갱신하는 진실 소스로 사용한다
- `response.delta`는 별도 `streamingText` 버퍼에 누적하고, `response.completed.final_response` 수신 시 최종 치환한다
- `approval.required.task.next_actions`로 CTA를 그린다
- `request.input_required.task.missing_inputs`로 인라인 폼을 그린다
- `approval.superseded` 수신 시 이전 카드 CTA를 disable하고 새 request로 focus 이동한다
- `follow=true` 연결이 끊기면 마지막 `sequence`로 재연결한다

### 추천 상태 머신

- planning: `request.created`, `context.hydrated`, `parsing.completed`
- approval: `approval.required`
- clarifying: `request.ambiguous`, `request.input_required`
- streaming: `response.started`, `response.delta`
- done: `response.completed`, `execution.completed`
- failed: `request.failed`, `execution.failed`
- cancelled: `approval.rejected`, `approval.superseded`

## 9. 현재 구현에서 나오지 않는 이벤트

기존 설계 문서에는 있지만, 2026-04-15 현재 구현에서 실제 emit되지 않는 이벤트:

- `classification.completed`
- `analysis.completed`
- `plan.started`
- `plan.delta`
- `approval.approved`
- `approval.expired`
- `execution.started`
- `execution.progress`
- `error`

프론트 구현 원칙:

- 위 이벤트를 기대해서 핵심 UX를 설계하면 안 된다
- 대신 현재 실제 이벤트만으로 UX를 완성해야 한다

## 10. 히스토리 API

SSE 외에 타임라인 조회 API도 있다.

- `GET /chatops/sessions/{session_id}/requests/{request_id}/events`

응답 shape:

```json
{
  "items": [
    {
      "sequence": 1,
      "type": "request.created",
      "data": {
        "type": "request.created",
        "phase": "request"
      },
      "timestamp": "2026-04-15T10:01:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

용도:

- 새로고침 후 타임라인 복구
- 모바일/백그라운드 복귀 시 초기 hydration
- 디버그 이벤트 패널
