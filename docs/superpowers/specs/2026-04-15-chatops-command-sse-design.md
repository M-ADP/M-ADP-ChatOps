# ChatOps Command SSE Conversational Streaming Design

**Date:** 2026-04-15
**Scope:** ChatOps backend contract and runtime only
**Frontend contract basis:** 2026-04-15 프론트 연결 구조 문서

## 목표

현재 프론트 계약을 유지한 채, `command` 요청도 실제 대화형 체감이 나도록 SSE 경로를 보강한다.

이번 변경의 핵심 목표는 세 가지다.

- `approval.required`, `request.input_required`, `request.ambiguous` 같은 구조화 이벤트를 그대로 유지한다.
- `command` 요청도 `request_id`를 먼저 반환한 뒤 SSE로 후속 상태를 받는 구조로 맞춘다.
- 구조화 상태 전이 위에 자연어 설명을 `response.delta`로 보조 스트림 처리한다.

## 현재 기준 계약

프론트는 아래 계약에 의존한다.

- 시작은 `POST /chatops/sessions/{session_id}/messages`
- 진행은 `GET /chatops/sessions/{session_id}/requests/{request_id}/stream?follow=true`
- 상태 전환은 SSE 구조화 이벤트를 기준으로 처리
- `response.delta`는 보조 텍스트로 누적
- `input_required` 보완은 별도 API가 아니라 후속 자연어 메시지 전송으로 처리

즉, 이번 설계는 프론트의 렌더링 기준을 바꾸는 작업이 아니라, 백엔드가 그 계약을 더 충실히 만족하게 만드는 작업이다.

## 현재 문제

### 1. `command`는 실질적으로 동기 처리다

현재 `inquiry`와 일부 `query`만 비동기 worker 경로를 탄다. 대부분의 `command`는 `POST /messages` 호출 동안 graph 실행을 마치고 응답을 반환한다.

이 구조에서는 프론트가 `request_id`를 받은 뒤 SSE를 열어도, 이미 완료된 이벤트를 재생하는 수준에 머문다. `response.delta`를 추가로 저장하더라도 진짜 실시간 스트림 체감은 나지 않는다.

### 2. `POST /messages` 응답 계약이 프론트 기대와 완전히 맞지 않는다

현재 백엔드는 최근 메시지 배열 중심 응답을 반환한다. 그러나 프론트 계약은 이 응답에서 곧바로 `request_id`를 확보해 SSE를 여는 흐름을 전제로 한다.

`command`를 비동기화하려면 이 응답에서 `request_id`를 안정적으로 제공해야 한다.

### 3. 사용자 설명과 기계 상태가 분리되어 있지 않다

프론트는 폼과 카드 상태를 구조화 이벤트로 처리하는 편이 안전하다. 반면 사용자는 "무엇이 필요하고", "무슨 계획으로 진행되고", "무엇이 생성되었는지"를 자연어로도 보고 싶어 한다.

현재는 이 두 층이 충분히 분리되어 있지 않다.

## 비목표

- 프론트 코드 변경
- `input_required` 전용 submit API 도입
- 새로운 SSE 엔드포인트 추가
- 기존 구조화 이벤트 제거 또는 이름 변경
- LLM 내부 단계 전체를 토큰 단위로 실시간 노출

## 선택한 접근

이번 변경은 `비동기 command + 보조 자연어 delta 스트림`으로 간다.

### 유지하는 것

- `request.created`
- `context.hydrated`
- `parsing.completed`
- `approval.required`
- `request.input_required`
- `request.ambiguous`
- `response.completed`
- `request.failed`
- `execution.completed`
- `execution.failed`
- `input_required` 보완을 후속 메시지로 처리하는 프론트 방식

### 바꾸는 것

- `command` 요청 생성도 비동기 worker 경로로 전환
- `POST /messages` 응답에서 `request_id`를 즉시 안정적으로 제공
- 최종 설명 문장을 `response.started` + `response.delta`로 먼저 적재한 뒤 구조화 상태 이벤트를 적재
- 승인 후 실행 경로에도 `execution.started`를 실제로 emit

## 설계 원칙

### 원칙 1. 구조화 이벤트가 상태의 단일 기준이다

프론트가 폼, 버튼, 카드 상태를 결정하는 기준은 계속 구조화 이벤트여야 한다.

- `approval.required`는 승인 UI 기준
- `request.input_required`는 추가 입력 폼 기준
- `request.ambiguous`는 선택지 UI 기준
- `response.completed`, `execution.completed`, `execution.failed`, `request.failed`는 종료 기준

자연어 스트림은 설명 계층일 뿐 상태 기준이 아니다.

### 원칙 2. `response.delta`는 보조 텍스트다

`response.delta`는 사용자에게 읽히는 설명을 제공하기 위한 것이다.

- 카드 렌더링의 필수 입력으로 사용하지 않는다.
- 상태 전이는 `status`, `phase`, `task`, `missing_inputs`로 판단한다.
- 프론트가 `response.delta`를 일부 놓쳐도 기능이 깨지면 안 된다.

### 원칙 3. `POST /messages`는 request 생성 응답이어야 한다

프론트가 SSE를 열 수 있으려면, 메시지 전송 응답에서 생성된 request를 식별할 수 있어야 한다.

따라서 `CreateSessionMessageResponse`는 기존 `messages` 배열을 유지하되, 아래 request 메타데이터를 additive 하게 노출한다.

- `request_id`
- `request_status`
- `request_type`
- `task`
- `final_response`

`messages`는 하위 호환용으로 유지하고, 프론트는 새 필드를 우선 사용하면 된다.

## API 계약 변경

### `POST /chatops/sessions/{session_id}/messages`

현재 응답은 최근 메시지 배열 중심이다. 이를 아래처럼 확장한다.

```json
{
  "request_id": 2001,
  "request_status": "processing",
  "request_type": "command",
  "final_response": null,
  "task": null,
  "messages": [
    {
      "message_id": "msg_user_01",
      "role": "user",
      "type": "text",
      "text": "demo 프로젝트 생성해"
    }
  ]
}
```

후보 상태:

- `processing`: 비동기 worker가 후속 처리를 맡는 상태
- `pending_approval`
- `input_required`
- `ambiguous`
- `completed`
- `failed`

이 설계의 목적은 프론트가 `messages` 배열 파싱 없이 `request_id`를 바로 잡게 만드는 것이다.

## SSE 계약 변경

### 변경하지 않는 이벤트

이벤트 이름과 기존 구조화 payload는 유지한다.

- `request.created`
- `context.hydrated`
- `parsing.completed`
- `approval.required`
- `request.input_required`
- `request.ambiguous`
- `response.completed`
- `request.failed`
- `execution.completed`
- `execution.failed`

### 추가 또는 활성화하는 이벤트

- `response.started`
  - 지금도 정의는 있으나, `command` 경로에서도 실제로 emit한다.
- `response.delta`
  - `command` 경로에서도 emit한다.
- `execution.started`
  - 승인 후 실행 시작 시 실제로 emit한다.

### `response.delta` payload 규칙

`command` 경로의 delta는 실제 토큰 스트림이 아닐 수도 있다. 프론트가 이 차이를 구분할 수 있도록 메타데이터를 추가한다.

```json
{
  "type": "response.delta",
  "request_id": 2001,
  "session_id": 1001,
  "text": "대상 프로젝트를 먼저 확인할게요.",
  "source": "final_response",
  "synthetic": true
}
```

권장 규칙:

- `synthetic=true`: 저장된 `final_response`를 chunking 해서 보낸 경우
- `synthetic=false`: 실제 모델 스트리밍 또는 실행 중 실시간 설명인 경우
- `source`
  - `model_stream`
  - `final_response`
  - `execution_summary`

프론트는 이 필드를 당장 사용하지 않아도 되지만, 향후 디버깅과 UX 분리에 도움이 된다.

## 상태별 이벤트 순서

### 1. 명령이 추가 입력을 요구하는 경우

1. `request.created`
2. `context.hydrated`
3. `parsing.completed`
4. `response.started`
5. `response.delta` 여러 개
6. `request.input_required`

설명 문장은 사용자가 바로 이해할 수 있는 내용이어야 한다.

- 어떤 값이 비어 있는지
- 어떤 형식으로 넣으면 되는지
- 현재까지 파악된 대상이 무엇인지

### 2. 명령이 승인 대기로 가는 경우

1. `request.created`
2. `context.hydrated`
3. `parsing.completed`
4. `response.started`
5. `response.delta` 여러 개
6. `approval.required`

설명 문장에는 아래를 포함할 수 있다.

- 어떤 작업을 하려는지
- 어느 프로젝트나 앱이 대상인지
- 리소스나 옵션이 무엇인지
- 승인하면 어떤 결과가 기대되는지

### 3. 명령이 모호한 경우

1. `request.created`
2. `context.hydrated`
3. `parsing.completed`
4. `response.started`
5. `response.delta` 여러 개
6. `request.ambiguous`

### 4. 명령이 즉시 완료되는 경우

1. `request.created`
2. `context.hydrated`
3. `parsing.completed`
4. `response.started`
5. `response.delta` 여러 개
6. `response.completed`

### 5. 명령이 실패하는 경우

1. `request.created`
2. `context.hydrated`
3. `parsing.completed`
4. `response.started`
5. `response.delta` 여러 개
6. `request.failed`

### 6. 승인 이후 실행 경로

1. `execution.started`
2. 선택적으로 `response.started`
3. 선택적으로 `response.delta` 여러 개
4. `execution.completed` 또는 `execution.failed`

승인 후의 자연어 설명은 "실행을 시작했다", "무엇을 만들고 있다", "접속 정보는 어디다" 같은 실행 중심 문장이어야 한다.

## 구현 상세

### 1. `command` 요청 생성 경로를 비동기화한다

대상 파일:

- `src/chatops/api/routers/requests.py`
- `src/chatops/api/routers/sessions.py`

설계:

- `preview_request()` 결과가 `command`여도 request row를 먼저 생성한다.
- 생성 직후 `status=processing` 또는 이에 준하는 초기 비단말 상태를 저장한다.
- 즉시 응답을 반환한다.
- graph 실행은 worker thread에서 수행한다.

이렇게 해야 프론트가 `request_id`를 받은 즉시 SSE를 열 수 있다.

### 2. worker 종료 시 상태별 구조화 이벤트를 emit한다

대상 함수:

- `_process_async_request()`
- `_append_request_resolution_events()`

설계:

- worker가 graph 결과를 저장한 뒤
- 필요하면 자연어 스트림 이벤트를 먼저 적재하고
- 마지막에 상태별 구조화 이벤트를 적재한다

`request.input_required`나 `approval.required`는 지금처럼 terminal 대용 상태 이벤트지만, 그 전에 읽을 수 있는 설명 텍스트가 추가된다.

### 3. synthetic delta 생성 헬퍼를 추가한다

대상 파일:

- `src/chatops/api/routers/requests.py`

새 책임:

- `final_response`를 적절한 문장 단위 또는 길이 단위로 자른다.
- `response.started`를 1회 emit한다.
- chunk별 `response.delta`를 emit한다.
- 빈 문자열, 공백-only, 중복 시작을 방지한다.

chunking 규칙은 사용자 체감 기준으로 단순해야 한다.

- 우선 문장 단위 분리
- 문장이 너무 길면 고정 길이 분할
- 이미 진짜 스트림이 발생한 요청에는 synthetic delta를 중복 emit하지 않음

### 4. 승인 후 경로에서 `execution.started`를 활성화한다

현재 코드에는 helper가 있으나 실제 호출이 없다.

대상 함수:

- `approve_request()`
- `_handle_natural_language_approval()`

설계:

- 승인 상태 전이를 성공시킨 직후 `execution.started`
- 이후 실행 결과를 저장하고 `execution.completed` 또는 `execution.failed`
- 필요 시 실행 설명용 `response.delta`를 중간에 emit

## `POST /messages` 응답 스키마 설계

`CreateSessionMessageResponse`는 기존 `messages` 배열을 유지하면서 아래 필드를 추가한다.

- `request_id: int | null`
- `request_status: str | null`
- `request_type: str | null`
- `final_response: str | null`
- `task: TaskSnapshot | null`

의도:

- 프론트는 `request_id`를 즉시 확보
- 기존 메시지 복원 흐름은 그대로 유지
- 비동기 `command`에서도 assistant 메시지 생성 시점을 기다리지 않음

## 오류 처리

### worker 실패

worker 내부 예외가 발생하면 아래를 보장한다.

- request status를 `failed`로 저장
- 사용자용 실패 메시지를 `final_response`에 기록
- `request.failed` emit
- 이후 세션 상세 조회에서도 같은 실패 상태가 보이도록 assistant message 동기화

### 중복 스트리밍 방지

실제 모델 스트리밍이 있었던 요청과 synthetic delta가 동시에 기록되면 프론트 텍스트가 중복된다.

따라서 worker 내부에는 아래 플래그가 필요하다.

- `stream_started`
- `stream_emitted_chunks`

실제 chunk가 하나라도 나갔으면 synthetic delta는 생략한다.

## 테스트 기준

### API 테스트

- `POST /messages`가 `request_id`를 즉시 반환하는지
- 비동기 `command`에서 초기 응답이 assistant 완성 메시지를 기다리지 않는지
- 기존 `messages` 배열 하위 호환이 유지되는지

### SSE 테스트

- `command` 요청이 `response.started`와 `response.delta`를 emit하는지
- `request.input_required`, `approval.required`, `request.ambiguous` 전에 delta가 저장되는지
- `execution.started`가 승인 후 실제로 emit되는지
- `synthetic`와 `source` 메타데이터가 포함되는지

### 회귀 테스트

- inquiry/query 기존 스트리밍이 깨지지 않는지
- terminal status 기준 follow stream 종료가 유지되는지
- 이벤트 sequence 단조 증가가 유지되는지
- `GET /events` replay가 새 이벤트를 그대로 복원하는지

## 위험과 대응

### 위험 1. `command` 비동기화로 기존 세션 메시지 테스트가 깨질 수 있다

기존 테스트는 `POST /messages` 응답에 assistant message가 즉시 포함된다고 가정한다.

대응:

- 응답 스키마를 additive 하게 확장
- 테스트를 `messages` 중심에서 `request_id` 중심으로 점진 전환
- 세션 상세 hydration은 기존 방식 유지

### 위험 2. synthetic delta가 너무 기계적으로 보일 수 있다

`final_response`를 임의 길이로 자르면 사용자 체감이 좋지 않다.

대응:

- 문장 경계를 우선 사용
- 한국어 조사나 마침표 기준 분할 우선
- 너무 짧은 chunk는 합친다

### 위험 3. 프론트가 `response.delta`를 상태 기준으로 오해할 수 있다

대응:

- 문서에 `response.delta`는 보조 텍스트라고 명시
- 구조화 이벤트를 항상 마지막 상태 전이 이벤트로 유지

## 구현 후 기대 결과

사용자 관점:

- "프로젝트 생성해. 그리고 애플리케이션 생성해." 같은 명령에서, 서버가 먼저 request를 만들고 대화형 설명을 스트림으로 보낸다.
- 입력이 더 필요하면 폼은 그대로 뜨고, 동시에 왜 필요한지 자연어로 설명된다.
- 승인 대기 상태에서는 어떤 작업을 할지 더 풍부하게 설명된다.
- 실행 완료 후에는 무엇이 생성됐고, 어디로 접속하면 되는지, 현재 상태가 무엇인지가 자연어와 구조화 상태로 함께 제공된다.

프론트 관점:

- 기존 카드 상태 머신은 유지된다.
- `response.delta`는 읽을 수 있는 설명이 늘어나는 정도로만 추가된다.
- `request_id` 확보 시점이 명확해진다.

백엔드 관점:

- `command`도 inquiry/query와 같은 request-first, stream-later 구조를 갖는다.
- 이벤트 적재 순서가 일관된다.
- 테스트가 스트리밍과 구조화 상태를 함께 검증하게 된다.
