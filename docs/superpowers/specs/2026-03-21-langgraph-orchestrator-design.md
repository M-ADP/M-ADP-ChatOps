# LangGraph 오케스트레이터 설계

## 목적

사용자 텍스트 요청을 문의, 조회, 명령으로 분류하고, 조회와 명령은 등록된 API를 이용해 처리하는 LangGraph 기반 오케스트레이션 서비스를 설계한다.

핵심 요구사항은 다음과 같다.

- 웹 API로 요청을 받는다.
- 대화 세션을 유지한다.
- 문의는 즉시 응답한다.
- 조회는 API 실행 후 현재 상태를 해석해서 응답한다.
- 명령은 실행 계획을 먼저 제시하고, 사용자 승인 후에만 실행한다.
- 응답은 request 단위 SSE 스트리밍으로 제공한다.
- 서비스는 MSA 환경의 독립 마이크로서비스로 동작한다.
- 서비스 전용 DB는 PostgreSQL을 사용한다.

## 상위 구조

구조는 `코어 엔진 + 어댑터 분리`로 간다.

- `웹 API 어댑터`
  - HTTP 요청 진입점
  - SSE 스트림 제공
  - 내부 사용자 헤더를 `AuthContext`로 변환
- `LangGraph 코어`
  - 요청 분류
  - 문의, 조회, 명령 분기
  - 계획 생성
  - 승인 대기
  - 승인 후 재개 및 실행
- `API 레지스트리 로더`
  - 등록된 API 메타데이터 로드
  - 후보 API 탐색
- `API 어댑터`
  - 실제 다운스트림 API 호출
  - 요청과 응답 정규화
- `영속성 계층`
  - 세션, 요청, 이벤트, 체크포인트 저장

전체 흐름은 다음과 같다.

`BFF/Gateway -> Web API -> LangGraph Core -> Persistence / API Adapter -> SSE 응답`

## 인터페이스 및 인증 전제

- 브라우저는 직접 이 서비스에 붙지 않고 앞단 `BFF/Gateway`를 거친다.
- 이 서비스는 내부 인증 헤더를 신뢰한다.
- 기본 헤더는 다음을 사용한다.
  - `X-User-Id`
  - `X-Request-Id`
  - 필요 시 `X-User-Role`, `X-Org-Id`
- 이 서비스는 세밀한 권한 정책 엔진을 직접 두지 않는다.
- 실제 권한 허용과 거부는 다운스트림 API가 결정한다.
- 이 서비스는 다운스트림의 `401`, `403`을 사용자 친화 메시지로 정리해서 전달한다.

## 요청 모델

### 세션

대화 맥락의 상위 단위다.

- `session_id`
- `user_id`
- `title`
- `status`
- `created_at`
- `updated_at`

세션 식별은 `user_id + session_id` 전제로 관리한다.

### 요청

세션 안의 개별 사용자 요청 단위다.

- `request_id`
- `session_id`
- `user_id`
- `message_text`
- `request_type`
- `intent`
- `classification_reason`
- `classification_confidence`
- `status`
- `requires_approval`
- `final_response`
- `created_at`
- `updated_at`

`요청 상태(Request.status)`는 다음 값을 가진다.

- `created`
- `classifying`
- `processing`
- `pending_approval`
- `approved`
- `rejected`
- `approval_expired`
- `executing`
- `completed`
- `failed`
- `cancelled`

### 요청 이벤트

SSE와 감사 로그의 기준 단위다.

- `event_id`
- `request_id`
- `session_id`
- `sequence`
- `event_type`
- `payload`
- `created_at`

### 그래프 체크포인트

LangGraph 재개를 위한 실행 상태 저장 단위다.

- `request_id`
- `thread_id`
- `checkpoint_id`
- `checkpoint_blob`
- `created_at`
- `updated_at`

## 요청 분류 정책

요청 분류는 `LLM 우선 + 정책 가드레일`로 처리한다.

- 기본 분류 대상
  - `inquiry`
  - `query`
  - `command`
- 함께 저장할 정보
  - `intent`
  - `classification_reason`
  - `classification_confidence`

가드레일은 다음과 같다.

- 시스템 변경 가능성이 있으면 `command`로 본다.
- 확신도가 낮으면 보수적으로 실패하거나 추가 정보가 필요하다고 응답한다.
- `command`는 무조건 계획 생성 후 승인 대기 상태로 진입한다.

## 유형별 처리 원칙

### 문의

- 추가 판단 없이 즉시 응답한다.
- 필요 시 등록된 API 설명을 참고해 답변한다.
- 실행은 하지 않는다.

### 조회

- 적절한 API를 찾는다.
- API를 호출한다.
- 자원 분석이나 모니터링 요청이면 결과를 해석한다.
- 단순 raw 결과가 아니라 현재 상태와 간단 판단을 함께 응답한다.

### 명령

- 적절한 API를 찾는다.
- 실행 계획을 생성한다.
- `pending_approval` 상태로 대기한다.
- 사용자가 승인한 경우에만 실행한다.
- 사용자가 승인하지 않으면 요청은 종료된다.

## 명령 상태 전이

명령 요청은 다음 상태 전이를 따른다.

`created -> classifying -> processing -> pending_approval -> approved -> executing -> completed`

예외 경로는 다음과 같다.

- 거절 시
  - `pending_approval -> rejected`
- 승인 대기 만료 시
  - `pending_approval -> approval_expired`
- 실행 실패 시
  - `executing -> failed`
- 실행 취소 시
  - `pending_approval -> cancelled`
  - `executing -> cancelled`

승인 API 규칙은 다음과 같다.

- `approve`는 `pending_approval` 상태에서만 허용한다.
- `reject`는 `pending_approval` 상태에서만 허용한다.
- 이미 `approved`, `rejected`, `approval_expired`, `completed`, `failed`, `cancelled` 상태인 요청에 다시 승인 또는 거절을 호출하면 `409`를 반환한다.
- `reject`가 호출되면 그래프는 재개하지 않고 종료한다.
- 명령이 `pending_approval`을 벗어난 뒤에는 동일 요청을 다시 실행하지 않는다.

## LangGraph 노드 구조

모든 요청은 같은 진입 경로를 가진다.

`ingest_request -> classify_request -> route_request`

이후 유형별로 분기한다.

### 문의 경로

`answer_inquiry -> complete_request`

### 조회 경로

`prepare_query -> execute_query -> interpret_result -> respond_query -> complete_request`

### 명령 경로

`plan_command -> wait_for_approval -> resume_after_approval -> execute_command -> respond_command -> complete_request`

핵심 노드는 다음과 같다.

### `ingest_request`

- 요청과 세션 유효성 확인
- `Request` 생성
- `request.created` 이벤트 기록

### `classify_request`

- Groq 모델로 요청 유형 분류
- `classification.completed` 이벤트 기록

### `prepare_query`

- API 후보 탐색
- 파라미터 해석

### `interpret_result`

- 자원 분석, 모니터링 결과를 사용자 응답용으로 요약
- 이상 여부나 간단한 해석 포함

### `plan_command`

- 실행 계획 생성
- 사용자에게 보여줄 단계별 계획 스트리밍

### `wait_for_approval`

- 상태를 `pending_approval`로 저장
- `approval.required` 이벤트 기록
- 그래프 실행 중단
- 체크포인트 저장

### `resume_after_approval`

- 승인 API 호출 시 저장된 체크포인트 기준으로 재개
- 거절 API 호출 시 `rejected`로 종료

### `execute_command`

- 실제 다운스트림 API 호출
- 진행 이벤트 기록

## API 레지스트리 전략

초기 버전에서는 기존 `apis/*.yaml` OpenAPI 문서를 원본 소스로 유지하고, AI가 실제로 선택과 실행 판단에 사용할 별도 operation 단위 메타데이터 파일을 함께 둔다.

현재 확인된 파일:

- `apis/project.yaml`
- `apis/application.yaml`
- `apis/monitoring.yaml`

1차 버전 전략은 다음과 같다.

- `apis/*.yaml`을 로딩한다.
- 각 OpenAPI operation별로 AI 메타데이터 파일을 둔다.
- OpenAPI에서 기계적으로 추출 가능한 필드는 자동 생성한다.
- 의도, 사용 조건, 위험도, 안전 규칙은 사람이 보강한다.
- LangGraph는 OpenAPI 원문이 아니라 변환된 `registry entry`와 AI 메타데이터를 보고 API 후보를 선택한다.
- Adapter는 선택된 operation의 호출을 담당한다.

이 방식의 장점은 다음과 같다.

- 이미 존재하는 OpenAPI YAML을 그대로 활용할 수 있다.
- API 설명과 파라미터 스키마를 재사용할 수 있다.
- AI가 읽기 쉬운 판단 레이어를 별도로 둘 수 있다.
- 추후 필요하면 별도 manifest 레이어를 추가해도 된다.

### 파일 구조

1차 버전 파일 구조는 다음 형태를 따른다.

- 원본 OpenAPI
  - `apis/project.yaml`
  - `apis/application.yaml`
  - `apis/monitoring.yaml`
- AI 메타데이터
  - `ai_registry/project.create.ai.yaml`
  - `ai_registry/project.list.ai.yaml`
  - `ai_registry/application.create.ai.yaml`
  - `ai_registry/monitoring.get_app_deployment_traffic.ai.yaml`

즉, 원본은 파일 단위로 유지하고 AI 메타데이터는 operation 단위로 분리한다.

### AI 메타데이터 필드

AI 메타데이터는 다음 필드를 가진다.

- `id`
  - operation의 고정 식별자
- `source_file`
  - 원본 OpenAPI 파일 경로
- `operation_id`
  - OpenAPI operationId
- `path`
  - 실제 API 경로
- `method`
  - HTTP 메서드
- `summary`
  - 원본 summary
- `capability`
  - 이 operation이 실제로 하는 일의 한 줄 설명
- `usable_in`
  - 어떤 요청 모드에서 사용할 수 있는지
  - 예: `query`, `command`
- `operation_kind`
  - `read`, `write`, `delete`, `action`
- `when_to_use`
  - 어떤 사용자 요청에 매핑해야 하는지
- `when_not_to_use`
  - 비슷하지만 쓰면 안 되는 경우
- `requires_confirmation`
  - 승인 필요 여부
- `risk_level`
  - `low`, `medium`, `high`
- `side_effects`
  - 실제 변경 사항
- `required_headers`
  - 호출에 필요한 헤더
- `required_inputs`
  - path, query, body를 포함한 필수 입력
- `preconditions`
  - 실행 전에 충족되어야 하는 조건
- `missing_info_questions`
  - 입력이 부족할 때 사용자에게 물어볼 질문
- `response_interpretation`
  - 응답을 사용자에게 어떻게 해석해 설명할지
- `plan_template`
  - 명령형 API 계획 생성 템플릿
- `examples`
  - 사용자 발화 예시

### 자동 생성과 수동 보강

OpenAPI에서 자동 생성하는 필드:

- `id`
- `source_file`
- `operation_id`
- `path`
- `method`
- `summary`
- `required_headers`
- `required_inputs`

`required_inputs`는 다음 구조를 따른다.

```yaml
required_inputs:
  headers:
    - name: X-User-Id
      required: true
      schema:
        type: string
  path:
    - name: project_id
      required: true
      schema:
        type: integer
  query: []
  body:
    required: true
    content_type: application/json
    schema_ref: "#/components/schemas/ProjectCreate"
```

### 재생성 규칙

- AI 메타데이터 파일은 canonical ID 기준 정렬로 생성한다.
- 자동 생성 필드는 재생성 시 덮어쓴다.
- 사람이 보강하는 필드는 기존 파일 값이 있으면 유지한다.
- 오래된 파일 삭제는 기본값으로 하지 않는다.

사람이 보강해야 하는 필드:

- `capability`
- `usable_in`
- `operation_kind`
- `when_to_use`
- `when_not_to_use`
- `requires_confirmation`
- `risk_level`
- `side_effects`
- `preconditions`
- `missing_info_questions`
- `response_interpretation`
- `plan_template`
- `examples`

### 안전 규칙

AI가 API를 선택할 때 다음 규칙을 강제한다.

- `query` 요청은 기본적으로 `operation_kind=read`만 후보가 된다.
- `read`가 아닌 operation은 `query` 경로에서 제외한다.
- `command` 요청만 `write`, `delete`, `action` operation을 후보로 삼을 수 있다.
- `requires_confirmation=true`인 operation은 반드시 명령 경로에서만 실행한다.
- `risk_level=high` operation은 승인 없이 실행하지 않는다.

즉, LLM 선택 이전에 operation 안전 필터링을 먼저 적용한다.

## API 어댑터 구조

Adapter는 실제 API 호출을 담당한다.

예상 책임은 다음과 같다.

- 다운스트림 URL 구성
- 내부 사용자 헤더 전달
- 요청 payload 매핑
- 응답 정규화
- 예외 정규화

출력은 공통 구조로 정리한다.

- `success`
- `normalized_result`
- `raw_response`
- `error_type`
- `error_message`

## API 표면

기본 API는 다음과 같다.

- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/requests`
- `GET /api/v1/sessions/{session_id}/requests/{request_id}`
- `GET /api/v1/sessions/{session_id}/requests/{request_id}/stream`
- `POST /api/v1/sessions/{session_id}/requests/{request_id}/approve`
- `POST /api/v1/sessions/{session_id}/requests/{request_id}/reject`

## SSE 계약

스트리밍은 `request` 단위로만 제공한다.

- 세션 전체 스트림은 1차 버전에 포함하지 않는다.
- 하나의 요청마다 하나의 SSE 스트림을 연다.
- 해당 요청의 이벤트만 전달한다.

대표 이벤트 타입은 다음과 같다.

- `request.created`
- `classification.completed`
- `response.started`
- `response.delta`
- `response.completed`
- `analysis.completed`
- `plan.started`
- `plan.delta`
- `approval.required`
- `approval.rejected`
- `approval.expired`
- `execution.started`
- `execution.progress`
- `execution.completed`
- `error`

운영 원칙:

- 이벤트는 전송 전에 DB에 먼저 저장한다.
- SSE는 `request_events`를 기반으로 흘린다.
- 연결이 끊겨도 상태의 진실 소스는 DB다.

### 재연결 규약

- 각 이벤트는 요청 내 단조 증가하는 `sequence`를 가진다.
- SSE `id:` 값은 `sequence`를 사용한다.
- 클라이언트는 재연결 시 `Last-Event-ID` 또는 `last_sequence` 기준으로 이후 이벤트를 다시 받을 수 있다.
- 서버는 `request_id + sequence` 순서로 이벤트를 반환한다.
- 중복 수신된 이벤트는 클라이언트가 `sequence` 기준으로 무시할 수 있어야 한다.
- 1차 버전에서도 최소한 `sequence` 기반 재생은 지원한다.

## 저장소 전략

이 서비스는 독립 마이크로서비스로 두고, 서비스 전용 DB는 PostgreSQL을 사용한다.

이유는 다음과 같다.

- LangGraph의 PostgreSQL 기반 체크포인터 공식 지원을 활용할 수 있다.
- 승인 대기 후 재개와 상태 저장을 프레임워크 지원 범위 안에서 처리하기 쉽다.
- 체크포인트 저장과 복구를 직접 커스텀 구현하는 부담을 줄일 수 있다.
- 이 서비스의 핵심은 CRUD보다 상태 저장, 재개, 스트리밍이므로 PostgreSQL 선택이 더 적합하다.

저장 대상은 다음과 같다.

- `sessions`
- `requests`
- `request_events`
- LangGraph checkpoint 관련 저장소

## 에러 처리 원칙

- 분류 실패 시 보수적으로 실패한다.
- 적절한 API를 못 찾으면 실행하지 않는다.
- 파라미터가 부족하면 명령 실행으로 넘어가지 않는다.
- 승인되지 않은 명령은 절대 실행하지 않는다.
- 다운스트림 `401`, `403`은 권한 부족으로 표준화한다.
- 다운스트림 `400`, `422`는 요청값 오류로 표준화한다.
- 다운스트림 `5xx`와 timeout은 일시 장애로 표준화한다.
- SSE 오류는 가능하면 `error` 이벤트로 기록 후 종료한다.

## 운영 규칙

- 모든 로그는 `user_id`, `session_id`, `request_id`를 포함한다.
- 명령 요청은 반드시 `pending_approval`을 거친다.
- 승인 API는 상태 전이 검사를 거친다.
- 같은 요청이 중복 실행되지 않도록 방지 장치가 필요하다.
- 조회는 제한적 재시도를 허용할 수 있다.
- 명령은 자동 재시도보다 재승인 기반 재실행을 우선한다.
- 승인 대기 요청은 만료 시간을 둘 수 있다.
- 만료 시 `approval_expired` 상태와 `approval.expired` 이벤트를 남긴다.

## 1차 버전 범위

포함:

- 텍스트 입력 기반 요청 처리
- 웹 API 진입점
- 대화 세션
- 문의, 조회, 명령 분류
- 조회 API 실행 및 결과 해석
- 명령 계획 생성
- 승인, 거절, 승인 후 재개
- request 단위 SSE
- `apis/*.yaml` 기반 API 레지스트리 로딩
- PostgreSQL 기반 상태 저장

제외:

- 파일 업로드
- 세션 전체 스트림
- 복잡한 권한 정책 엔진
- 복수 승인자 워크플로우
- 운영자 UI
- 장시간 백그라운드 워커 고도화

## 구현 시 주의점

- BFF가 앞단에 있으므로 브라우저 직접 인증 문제는 BFF에서 처리한다.
- 이 서비스는 내부 사용자 컨텍스트를 안전하게 전달하는 데 집중한다.
- OpenAPI YAML은 사람이 읽는 문서이자 기계가 읽는 registry 소스다.
- LangGraph 핵심 상태와 서비스 요청 상태를 분리하지 말고, 요청 단위 추적을 중심으로 설계한다.

## 결정 요약

- 웹 API 기반으로 시작한다.
- `코어 엔진 + 어댑터 분리` 구조를 사용한다.
- 대화 세션은 필수다.
- 요청 분류는 `LLM 우선 + 정책 가드레일`이다.
- 명령은 계획 생성 후 사용자 승인 뒤 실행한다.
- 스트리밍은 request 단위 SSE만 지원한다.
- 앞단은 BFF/Gateway다.
- API 설명 소스는 현재의 `apis/*.yaml`을 사용한다.
- 이 서비스는 독립 마이크로서비스로 두고, 서비스 전용 DB는 PostgreSQL로 간다.
