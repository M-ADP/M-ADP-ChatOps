# LangGraph 오케스트레이터 서비스 구현 계획

> **에이전트 작업 규칙:** 이 계획을 구현할 때는 반드시 `superpowers:subagent-driven-development`(subagent 사용 가능 시) 또는 `superpowers:executing-plans`를 사용한다. 진행 상황은 체크박스(`- [ ]`)로 관리한다.

**목표:** 요청 유형을 분류하고, 세션/요청 상태를 PostgreSQL에 저장하며, request 단위 SSE 스트리밍과 명령 승인 후 실행 흐름을 제공하는 FastAPI 기반 LangGraph 오케스트레이션 서비스를 구현한다.

**아키텍처:** `apis/*.yaml`과 `ai_registry/*.ai.yaml`을 API capability source로 유지하고, 버전드 FastAPI API를 노출하며, 오케스트레이션 로직은 `chatops` 패키지 아래로 분리한다. 현재 상태와 이벤트 이력은 PostgreSQL에 저장하고, LangGraph + PostgreSQL checkpoint를 사용해 승인 대기와 재개를 처리한다. SSE는 저장된 `request_events`를 그대로 흘려주는 얇은 projection 레이어로 유지한다.

**기술 스택:** Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, psycopg, LangGraph, langgraph-checkpoint-postgres, httpx, PyYAML, pytest

---

## 파일 구조

서비스는 아래 구조로 구현한다.

- `main.py`
  - FastAPI 앱을 import/export 하는 프로세스 진입점
- `requirements.txt`
  - 런타임 및 테스트 의존성 목록
- `src/chatops/__init__.py`
  - 패키지 마커
- `src/chatops/app.py`
  - `create_app()` 팩토리와 라우터 등록
- `src/chatops/config.py`
  - DB, Groq, downstream base URL, timeout, approval TTL 설정 모델
- `src/chatops/api/dependencies.py`
  - DB session, auth context, registry, graph service 같은 request scope dependency
- `src/chatops/api/routers/__init__.py`
  - 버전드 라우터 조립
- `src/chatops/api/routers/health.py`
  - 헬스체크 엔드포인트
- `src/chatops/api/routers/sessions.py`
  - 세션 생성/조회 엔드포인트
- `src/chatops/api/routers/requests.py`
  - 요청 생성/조회/승인/거절 엔드포인트
- `src/chatops/api/routers/stream.py`
  - request 단위 SSE 엔드포인트
- `src/chatops/schemas/auth.py`
  - 내부 헤더 기반 `AuthContext` DTO
- `src/chatops/schemas/sessions.py`
  - 세션 요청/응답 DTO
- `src/chatops/schemas/requests.py`
  - 요청 생성/조회/승인/거절 DTO
- `src/chatops/schemas/events.py`
  - SSE 이벤트 DTO
- `src/chatops/domain/enums.py`
  - 요청 유형, 요청 상태, 이벤트 타입 enum
- `src/chatops/db/base.py`
  - SQLAlchemy declarative base와 metadata
- `src/chatops/db/session.py`
  - engine과 session factory
- `src/chatops/db/models.py`
  - sessions, requests, request_events SQLAlchemy 모델
- `src/chatops/db/repositories.py`
  - 세션/요청/이벤트 CRUD helper
- `alembic.ini`
  - Alembic CLI 설정
- `migrations/env.py`
  - Alembic runtime 환경
- `migrations/versions/0001_initial_chatops_tables.py`
  - sessions, requests, request_events 초기 스키마 마이그레이션
- `src/chatops/services/registry.py`
  - `ai_registry/*.ai.yaml` 로딩, safety filter 적용, 후보 선택
- `src/chatops/services/auth.py`
  - `X-User-*` 헤더를 `AuthContext`로 파싱
- `src/chatops/services/llm.py`
  - Groq 기반 분류/응답 생성 인터페이스
- `src/chatops/services/adapters.py`
  - metadata + OpenAPI source 기반 downstream API 실행
- `src/chatops/services/events.py`
  - request event append와 sequence 기반 replay 지원
- `src/chatops/graph/state.py`
  - LangGraph state 정의
- `src/chatops/graph/nodes.py`
  - 그래프 노드 구현
- `src/chatops/graph/workflow.py`
  - 그래프 조립과 checkpoint wiring
- `src/chatops/graph/service.py`
  - API 레이어에서 사용하는 orchestrator facade
- `tests/conftest.py`
  - app, DB, registry, fake LLM, fake adapter 공통 fixture
- `tests/test_api_health.py`
  - health endpoint 테스트
- `tests/test_config.py`
  - 설정 및 환경 변수 파싱 테스트
- `tests/test_api_sessions.py`
  - 세션 생성/조회 테스트
- `tests/test_api_requests.py`
  - 요청 생성/조회/승인/거절 테스트
- `tests/test_sse_stream.py`
  - SSE 스트리밍과 replay 테스트
- `tests/test_registry_service.py`
  - 후보 선택과 safety filter 테스트
- `tests/test_graph_service.py`
  - inquiry/query/command 상태 전이 테스트
- `tests/test_adapter_service.py`
  - downstream 호출 정규화 테스트
- `.env.example`
  - 필요한 환경 변수와 예시 값

## API 목록

| # | Method | Path | 설명 | 인증 | 응답 코드 |
|---|--------|------|------|------|-----------|
| 1 | GET | `/health` | 헬스체크 | - | 200 |
| 2 | POST | `/sessions` | 세션 생성 | X-User-Id | 201 |
| 3 | GET | `/sessions/{session_id}` | 세션 조회 | X-User-Id | 200 |
| 4 | POST | `/sessions/{session_id}/requests` | 요청 생성 (자연어 승인/거절 포함) | X-User-Id | 202 |
| 5 | GET | `/sessions/{session_id}/requests/{request_id}` | 요청 조회 | X-User-Id | 200 |
| 6 | POST | `/sessions/{session_id}/requests/{request_id}/approve` | 명시적 요청 승인 | X-User-Id | 200 |
| 7 | POST | `/sessions/{session_id}/requests/{request_id}/reject` | 명시적 요청 거절 | X-User-Id | 200 |
| 8 | GET | `/sessions/{session_id}/requests/{request_id}/stream` | SSE 이벤트 스트리밍 | X-User-Id | 200 |

**공통 규칙:**
- 모든 엔드포인트(health 제외)는 `X-User-Id` 헤더 필수
- `user_id + session_id` 소유권 검사 강제
- `approve/reject`는 `pending_approval` 상태에서만 허용, 중복 시 `409`
- SSE는 `Last-Event-ID` 기반 replay 지원

**SSE 이벤트 타입:** `request.created`, `approval.required`, `response.completed`, `execution.completed`, `execution.failed`, `approval.rejected`

---

## 청크 1: 서비스 골격

### 작업 1: 샘플 진입점을 FastAPI 앱 팩토리와 health 라우트로 교체

**파일:**
- Modify: `main.py`
- Create: `src/chatops/__init__.py`
- Create: `src/chatops/app.py`
- Create: `src/chatops/api/routers/__init__.py`
- Create: `src/chatops/api/routers/health.py`
- Test: `tests/test_api_health.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from fastapi.testclient import TestClient

from chatops.app import create_app



def test_healthcheck_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_api_health.py -v`
예상 결과: `chatops` 패키지와 health 라우터가 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

구현 항목:

- `src/chatops/app.py`에 `create_app()` 구현
- `src/chatops/api/routers/__init__.py`에 버전드 라우터 조립 구현
- `src/chatops/api/routers/health.py`에 `GET /health` 구현
- `main.py`를 아래 형태로 교체

```python
from chatops.app import create_app


app = create_app()
```

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_api_health.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

### 작업 2: 설정과 dependency bootstrap 추가

**파일:**
- Modify: `requirements.txt`
- Create: `.env.example`
- Create: `src/chatops/config.py`
- Create: `src/chatops/api/dependencies.py`
- Test: `tests/test_config.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from chatops.config import Settings



def test_settings_have_required_defaults() -> None:
    settings = Settings()

    assert settings.request_stream_keepalive_seconds == 15
    assert settings.approval_ttl_seconds == 900
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_config.py -v`
예상 결과: 설정 모델이 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

`requirements.txt`에 아래 의존성 추가:

```text
fastapi
uvicorn
pydantic-settings
sqlalchemy
psycopg[binary]
alembic
langgraph
langgraph-checkpoint-postgres
httpx
PyYAML
pytest
```

`src/chatops/config.py`에 아래 기본값을 가진 `Settings` 구현:

- `database_url`
- `groq_api_key`
- `groq_model`
- `request_stream_keepalive_seconds=15`
- `approval_ttl_seconds=900`
- `downstream_timeout_seconds=10`

`.env.example`에는 placeholder 값을 작성한다.

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_config.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

## 청크 2: 영속성과 레지스트리

### 작업 3: PostgreSQL 모델과 repository 레이어 구현

**파일:**
- Create: `tests/conftest.py`
- Create: `src/chatops/domain/enums.py`
- Create: `src/chatops/db/base.py`
- Create: `src/chatops/db/session.py`
- Create: `src/chatops/db/models.py`
- Create: `src/chatops/db/repositories.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/0001_initial_chatops_tables.py`
- Test: `tests/test_api_sessions.py`
- Test: `tests/test_api_requests.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from chatops.db.repositories import SessionRepository



def test_create_session_persists_owner(db_session) -> None:
    repo = SessionRepository(db_session)

    session = repo.create(user_id="user-1", title=None)

    assert session.user_id == "user-1"
    assert session.status == "active"
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_api_sessions.py -v`
예상 결과: DB 모델과 repository가 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

SQLAlchemy 모델 구현:

- `SessionRecord`
- `RequestRecord`
- `RequestEventRecord`

필수 컬럼:

- `sessions(id, user_id, title, status, created_at, updated_at)`
- `requests(id, session_id, user_id, message_text, request_type, status, requires_approval, final_response, created_at, updated_at)`
- `request_events(id, request_id, session_id, sequence, event_type, payload, created_at)`

repository helper 구현:

- `SessionRepository.create()`
- `SessionRepository.get_for_user()`
- `RequestRepository.create()`
- `RequestRepository.get_for_user()`
- `RequestRepository.update_status()`
- `RequestEventRepository.append()`
- `RequestEventRepository.list_after_sequence()`

`tests/conftest.py`에 아래 fixture 추가:

- repository/API 테스트용 빠른 unit-test DB session fixture
- Task 10의 checkpoint integration용 PostgreSQL DSN fixture

운영 환경에서 `metadata.create_all()`에 의존하지 않도록 초기 스키마 Alembic 자산도 함께 추가한다.

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_api_sessions.py tests/test_api_requests.py -v`
예상 결과: repository 수준 테스트 PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

### 작업 4: AI registry 로딩과 요청 모드별 safety filter 구현

**파일:**
- Create: `src/chatops/services/registry.py`
- Test: `tests/test_registry_service.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from chatops.services.registry import RegistryService



def test_query_mode_returns_only_read_operations() -> None:
    service = RegistryService.from_directory("ai_registry")

    candidates = service.find_candidates("프로젝트 목록 보여줘", usable_in="query")

    assert candidates
    assert all(candidate.operation_kind == "read" for candidate in candidates)
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_registry_service.py -v`
예상 결과: registry service가 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

구현 항목:

- `ai_registry/*.ai.yaml` 로딩
- immutable registry entry 모델
- `find_candidates(user_text, usable_in)` API
- safety rule 적용
  - `usable_in="query"`면 `operation_kind="read"`만 반환
  - `usable_in="command"`면 `write`, `delete`, `action` 반환
  - `requires_confirmation=true`인 항목은 `query` 후보에서 제외

이번 반복에서는 embedding 없이 단순 lexical matching만 사용한다.

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_registry_service.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

## 청크 3: LangGraph 코어

### 작업 5: AuthContext, session/request DTO, API 계약 정의

**파일:**
- Create: `src/chatops/schemas/auth.py`
- Create: `src/chatops/schemas/sessions.py`
- Create: `src/chatops/schemas/requests.py`
- Create: `src/chatops/schemas/events.py`
- Create: `src/chatops/services/auth.py`
- Modify: `src/chatops/api/dependencies.py`
- Test: `tests/test_api_sessions.py`
- Test: `tests/test_api_requests.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from fastapi.testclient import TestClient

from chatops.app import create_app



def test_create_session_requires_x_user_id() -> None:
    client = TestClient(create_app())

    response = client.post("/sessions", json={})

    assert response.status_code == 401
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_api_sessions.py tests/test_api_requests.py -v`
예상 결과: auth 추출과 DTO가 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

구현 항목:

- `user_id`, `request_id`, optional `user_role`, optional `org_id`를 가진 `AuthContext`
- `X-User-Id`, `X-Request-Id`, `X-User-Role`, `X-Org-Id` 헤더 파싱
- 아래 요청/응답 DTO
  - 세션 생성
  - 세션 조회
  - 요청 생성
  - 요청 조회
  - 승인
  - 거절
- `sequence`, `type`, `data`, `timestamp`를 가진 SSE event DTO

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_api_sessions.py tests/test_api_requests.py -v`
예상 결과: auth와 schema 계약 테스트 PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

### 작업 6: LangGraph state와 inquiry/query/command 워크플로 스켈레톤 구현

**파일:**
- Create: `src/chatops/services/llm.py`
- Create: `src/chatops/graph/state.py`
- Create: `src/chatops/graph/nodes.py`
- Create: `src/chatops/graph/workflow.py`
- Create: `src/chatops/graph/service.py`
- Test: `tests/test_graph_service.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from chatops.graph.service import GraphService



def test_inquiry_completes_without_approval(fake_graph_service: GraphService) -> None:
    result = fake_graph_service.handle_request(
        session_id="session-1",
        user_id="user-1",
        message_text="프로젝트 생성 방법 알려줘",
    )

    assert result.status == "completed"
    assert result.requires_approval is False



def test_query_returns_interpreted_response(fake_graph_service: GraphService) -> None:
    result = fake_graph_service.handle_request(
        session_id="session-1",
        user_id="user-1",
        message_text="현재 앱 트래픽 상태 알려줘",
    )

    assert result.status == "completed"
    assert result.final_response



def test_command_request_stops_at_pending_approval(fake_graph_service: GraphService) -> None:
    result = fake_graph_service.handle_request(
        session_id="session-1",
        user_id="user-1",
        message_text="프로젝트 생성해줘",
    )

    assert result.status == "pending_approval"
    assert result.requires_approval is True
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_graph_service.py -v`
예상 결과: graph service가 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

graph state 필드 구현:

- `request_id`
- `session_id`
- `user_id`
- `message_text`
- `request_type`
- `request_status`
- `intent`
- `classification_reason`
- `classification_confidence`
- `selected_operation_ids`
- `final_response`

노드 스켈레톤 구현:

- `ingest_request`
- `classify_request`
- `route_request`
- `answer_inquiry`
- `prepare_query`
- `execute_query`
- `interpret_result`
- `plan_command`
- `wait_for_approval`
- `resume_after_approval`
- `execute_command`
- `respond_command`

테스트에서는 fake classifier와 fake adapter를 사용하고, Groq 실네트워크 호출에 결합하지 않는다.

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_graph_service.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

## 청크 4: API 표면과 SSE

### 작업 7: FastAPI session/request API 노출

**파일:**
- Create: `src/chatops/api/routers/sessions.py`
- Create: `src/chatops/api/routers/requests.py`
- Modify: `src/chatops/api/routers/__init__.py`
- Test: `tests/test_api_sessions.py`
- Test: `tests/test_api_requests.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from fastapi.testclient import TestClient

from chatops.app import create_app



def test_create_request_returns_processing_status() -> None:
    client = TestClient(create_app())
    session = client.post("/sessions", headers={"X-User-Id": "user-1"}, json={}).json()

    response = client.post(
        f"/sessions/{session['session_id']}/requests",
        headers={"X-User-Id": "user-1"},
        json={"message": "프로젝트 생성해줘"},
    )

    assert response.status_code == 202
    assert response.json()["status"] in {"processing", "pending_approval"}
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_api_sessions.py tests/test_api_requests.py -v`
예상 결과: session/request 라우터가 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

아래 API 노출:

- `POST /sessions`
- `GET /sessions/{session_id}`
- `POST /sessions/{session_id}/requests`
- `GET /sessions/{session_id}/requests/{request_id}`
- `POST /sessions/{session_id}/requests/{request_id}/approve`
- `POST /sessions/{session_id}/requests/{request_id}/reject`

규칙:

- `user_id + session_id` 소유권 검사 강제
- `approve/reject`는 `pending_approval` 상태에서만 허용
- 중복 `approve/reject`는 `409` 반환

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_api_sessions.py tests/test_api_requests.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

### 작업 8: request 단위 SSE 스트리밍과 sequence replay 구현

**파일:**
- Create: `src/chatops/api/routers/stream.py`
- Create: `src/chatops/services/events.py`
- Modify: `src/chatops/app.py`
- Test: `tests/test_sse_stream.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
def test_request_stream_replays_events_after_sequence(client, seeded_request_event) -> None:
    response = client.get(
        f"/sessions/{seeded_request_event.session_id}/requests/{seeded_request_event.request_id}/stream",
        headers={"X-User-Id": "user-1", "Last-Event-ID": "1"},
    )

    body = response.text

    assert "event: response.delta" in body
    assert "id: 2" in body
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_sse_stream.py -v`
예상 결과: stream 라우터와 event replay가 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

구현 항목:

- request-local monotonic `sequence`를 갖는 append-only event writer
- `GET /sessions/{session_id}/requests/{request_id}/stream` SSE 엔드포인트
- SSE `id:` 값을 `sequence`로 설정
- `Last-Event-ID` 기준 replay
- `request_stream_keepalive_seconds`마다 keepalive comment 전송

이번 계획에서는 session-wide stream을 구현하지 않는다.

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_sse_stream.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

## 청크 5: Downstream 실행과 승인 재개

### 작업 9: 범용 downstream adapter 실행과 오류 정규화 구현

**파일:**
- Create: `src/chatops/services/adapters.py`
- Test: `tests/test_adapter_service.py`
- Test: `tests/test_graph_service.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from chatops.services.adapters import AdapterResult, DownstreamAdapterService



def test_permission_denied_is_normalized(fake_http_client) -> None:
    service = DownstreamAdapterService(fake_http_client)

    result = service.execute(
        method="POST",
        path="/projects",
        headers={"X-User-Id": "user-1"},
        json_body={"name": "demo"},
    )

    assert result.success is False
    assert result.error_type == "permission_denied"
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_adapter_service.py tests/test_graph_service.py -v`
예상 결과: adapter service가 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

adapter 계약 구현:

- 입력: metadata entry, auth context, resolved params
- 출력: `success`, `normalized_result`, `raw_response`, `error_type`, `error_message`

오류 정규화 규칙:

- `401`, `403` -> `permission_denied`
- `400`, `422` -> `bad_request`
- `404` -> `not_found`
- timeout -> `timeout`
- `5xx` -> `downstream_unavailable`

`httpx.AsyncClient`를 사용하고 테스트에는 fake client를 주입한다.

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_adapter_service.py tests/test_graph_service.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

### 작업 10: approval pause/resume용 PostgreSQL checkpoint wiring

**파일:**
- Modify: `src/chatops/graph/workflow.py`
- Modify: `src/chatops/graph/service.py`
- Modify: `src/chatops/services/events.py`
- Test: `tests/test_graph_service.py`
- Test: `tests/test_api_requests.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
def test_approve_resumes_existing_command_from_checkpoint(client, pending_command_request) -> None:
    response = client.post(
        f"/sessions/{pending_command_request.session_id}/requests/{pending_command_request.id}/approve",
        headers={"X-User-Id": pending_command_request.user_id},
    )

    assert response.status_code == 200
    assert response.json()["status"] in {"approved", "executing", "completed"}
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_graph_service.py tests/test_api_requests.py -v`
예상 결과: approval resume wiring이 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

구현 항목:

- 앱 시작 시 PostgreSQL checkpointer setup
- request별 stable `thread_id`
- `wait_for_approval`에서 pause
- `approve` 호출 시 저장된 checkpoint부터 resume
- `reject` 호출 시 요청을 `rejected`로 전환하고 `approval.rejected` 이벤트 발행
- 만료된 승인 요청은 `approval_expired`로 전환

idempotency 유지:

- 요청이 `pending_approval`을 벗어난 뒤 중복 `approve/reject`는 `409` 반환

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_graph_service.py tests/test_api_requests.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

## 청크 6: 최종 검증과 문서 정리

### 작업 11: 종단 간 동작 검증과 문서 갱신

**파일:**
- Modify: `docs/superpowers/specs/2026-03-21-langgraph-orchestrator-design.md`
- Modify: `.env.example`
- Verify: `tests/*.py`
- Verify: `ai_registry/*.ai.yaml`

- [ ] **단계 1: API/graph 중심 테스트 실행**

실행: `.venv/bin/python -m pytest tests/test_api_health.py tests/test_config.py tests/test_api_sessions.py tests/test_api_requests.py tests/test_sse_stream.py tests/test_registry_service.py tests/test_graph_service.py tests/test_adapter_service.py -v`
예상 결과: PASS

- [ ] **단계 2: 전체 테스트 실행**

실행: `.venv/bin/python -m pytest tests -v`
예상 결과: PASS

- [ ] **단계 3: 수동 smoke flow 확인**

실행:

```bash
.venv/bin/python -m uvicorn main:app --reload
```

수동 검증 항목:

- `POST /sessions`
- `POST /sessions/{id}/requests` with inquiry text
- `POST /sessions/{id}/requests` with query text
- `POST /sessions/{id}/requests` with command text
- `GET /sessions/{id}/requests/{request_id}/stream`
- `POST /approve`
- `POST /reject`

- [ ] **단계 4: 구현과 설계 문서 동기화**

구현 과정에서 이름이나 API 계약이 바뀐 부분만 설계 문서에 반영한다. 안정적인 섹션은 불필요하게 다시 쓰지 않는다.

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

---

계획 문서를 `docs/superpowers/plans/2026-03-21-langgraph-orchestrator-service.md`에 저장했다. 실행 준비가 되면 이 계획 기준으로 바로 구현을 시작한다.
