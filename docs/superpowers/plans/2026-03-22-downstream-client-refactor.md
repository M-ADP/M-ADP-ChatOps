# Downstream Client 구조 정렬 구현 계획

> **에이전트 작업 규칙:** 이 계획을 구현할 때는 반드시 `superpowers:subagent-driven-development`(subagent 사용 가능 시) 또는 `superpowers:executing-plans`를 사용한다. 진행 상황은 체크박스(`- [ ]`)로 관리한다.

**목표:** ChatOps의 downstream 호출 계층을 `M-ADP-PROJECT dev-0.1.23`와 유사한 `common/config`, `core/client`, `dependencies/client`, `infra/client` 구조로 재구성하고, generic adapter를 concrete project/application/monitoring client 조합으로 대체한다.

**아키텍처:** 기존 `DownstreamAdapterService`의 generic HTTP 호출 책임을 해체하고, operation id 기반 dispatch table과 도메인별 client interface를 도입한다. API dependency는 fake/real client를 선택하고, graph는 얇은 dispatcher만 의존하도록 변경한다. 환경 변수 로딩은 `/vault/secrets/.env` 우선 규칙을 유지하면서 서버별 config 파일로 분리한다.

**기술 스택:** Python 3.12+, FastAPI, Pydantic v2, Pydantic Settings, aiohttp, LangGraph, SQLAlchemy, pytest

---

## Chunk 1: Dispatch 계약 고정

### 작업 1: operation id -> client method dispatch table을 테스트로 고정

**파일:**
- Create: `tests/test_downstream_dispatch.py`
- Modify: `tests/test_graph_service.py`

- [ ] `project.create`, `project.list_projects`, `application.create_apps`, `monitoring.get_app_deployment_traffic`가 각각 올바른 도메인 client method로 매핑되는 실패 테스트를 작성한다.
- [ ] 해당 테스트만 실행해서 현재 generic adapter 구조에서 실패를 확인한다.
- [ ] 테스트 failure 메시지가 dispatch 부재 때문인지 검증한다.
- [ ] 파일 단위 커밋을 수행한다.

## Chunk 2: Config / Client 구조 분리

### 작업 2: ref repo 스타일의 config와 client interface를 추가

**파일:**
- Create: `src/chatops/common/config/settings.py`
- Create: `src/chatops/common/config/project_server.py`
- Create: `src/chatops/common/config/application_server.py`
- Create: `src/chatops/common/config/monitoring_server.py`
- Create: `src/chatops/core/client/http.py`
- Create: `src/chatops/core/client/project.py`
- Create: `src/chatops/core/client/application.py`
- Create: `src/chatops/core/client/monitoring.py`
- Create: `src/chatops/infra/client/asyncio_http.py`
- Create: `src/chatops/infra/client/fake_project_impl.py`
- Create: `src/chatops/infra/client/fake_application_impl.py`
- Create: `src/chatops/infra/client/fake_monitoring_impl.py`
- Modify: `tests/test_config.py`

- [ ] 서버별 config와 fake toggle 동작에 대한 실패 테스트를 작성한다.
- [ ] 공통 env 로더와 LoggedSettings 성격의 베이스를 추가한다.
- [ ] project/application/monitoring client protocol과 fake 구현을 추가한다.
- [ ] 테스트를 재실행해 통과를 확인한다.
- [ ] 파일 단위 커밋을 수행한다.

## Chunk 3: Real client / dependency wiring

### 작업 3: real client 구현과 dependency client 선택을 연결

**파일:**
- Create: `src/chatops/dependencies/client/project.py`
- Create: `src/chatops/dependencies/client/application.py`
- Create: `src/chatops/dependencies/client/monitoring.py`
- Create: `src/chatops/infra/client/project_impl.py`
- Create: `src/chatops/infra/client/application_impl.py`
- Create: `src/chatops/infra/client/monitoring_impl.py`
- Modify: `src/chatops/api/dependencies.py`
- Modify: `tests/test_dependencies.py`

- [ ] fake/real client 선택 실패 테스트를 작성한다.
- [ ] 참조 레포와 유사한 dependency 패턴으로 client 선택 함수를 구현한다.
- [ ] aiohttp 기반 real client 구현을 추가한다.
- [ ] 테스트를 재실행해 통과를 확인한다.
- [ ] 파일 단위 커밋을 수행한다.

## Chunk 4: Graph dispatcher 교체

### 작업 4: generic adapter 제거 후 graph가 concrete client dispatcher를 사용하도록 변경

**파일:**
- Create: `src/chatops/services/downstream_dispatcher.py`
- Modify: `src/chatops/graph/service.py`
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/graph/state.py`
- Modify: `tests/test_graph_service.py`
- Modify: `tests/test_api_requests.py`

- [ ] graph가 generic adapter가 아닌 concrete dispatcher를 쓰는 실패 테스트를 작성한다.
- [ ] operation id 기반 dispatcher를 구현한다.
- [ ] graph/service wiring을 교체하고 기존 기능을 유지한다.
- [ ] 테스트를 재실행해 통과를 확인한다.
- [ ] 파일 단위 커밋을 수행한다.

## Chunk 5: 검증

### 작업 5: 회귀 및 실제 실행 검증

**파일:**
- Modify: `docs/superpowers/specs/2026-03-21-langgraph-orchestrator-design.md`
- Modify: `docs/superpowers/plans/2026-03-21-langgraph-orchestrator-service.md`

- [ ] 전체 테스트를 실행한다.
- [ ] PostgreSQL 기준 migration과 서버 기동을 확인한다.
- [ ] `M-ADP-PROJECT` 실제 downstream command/query smoke를 다시 수행한다.
- [ ] 문서를 현재 구조에 맞게 갱신한다.
- [ ] 파일 단위 커밋을 수행한다.
