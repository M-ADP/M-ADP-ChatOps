# ChatOps 백엔드 오케스트레이션 100% 설계

## 목적

이 문서는 현재 ChatOps 백엔드 오케스트레이션의 구현 상태를 기준으로, `핵심 백엔드 오케스트레이션 100%`에 도달하기 위해 무엇이 완료되었고 무엇이 남아 있는지를 정리한다.

여기서 말하는 100%는 다음을 의미한다.

- 설계한 오케스트레이션 구조가 코드로 구현되어 있다.
- 핵심 API와 상태 전이가 실제로 동작한다.
- fake 환경뿐 아니라 real downstream 환경에서도 주요 시나리오가 검증되어 있다.
- 운영 기준에서 필요한 예외 처리, 재개, 재연결, 관측성이 빠지지 않았다.

## 현재 완료된 것

### 웹 API와 상태 모델

- FastAPI 기반 웹 API 진입점이 구현되어 있다.
- 세션 생성/조회 API가 구현되어 있다.
- 요청 생성/조회/승인/거절 API가 구현되어 있다.
- request 단위 SSE 스트림 API가 구현되어 있다.
- `sessions`, `requests`, `request_events` 모델이 구현되어 있다.
- Sonyflake bigint ID 전략이 적용되어 있다.

### LangGraph 오케스트레이션

- `inquiry`, `query`, `command` 분기 흐름이 구현되어 있다.
- `plan_command -> wait_for_approval -> resume -> execute_command` 흐름이 구현되어 있다.
- `langgraph-checkpoint-postgres` 기반 pause/resume 구조가 연결되어 있다.
- 승인/거절 시 상태 전이가 구현되어 있다.
- request 단위 상태와 그래프 상태가 함께 동작한다.

### 레지스트리와 파라미터 해석

- `apis/*.yaml`과 `ai_registry/*.ai.yaml` 기반 레지스트리 로딩이 구현되어 있다.
- operation 단위 후보 선택이 구현되어 있다.
- 중요 비즈니스 파라미터 수집 기준이 구현되어 있다.
- 이름 + 세션 문맥 기반 대상 해석이 구현되어 있다.
- 내부 `project_id`, `application_id`를 사용자에게 요구하지 않도록 구현되어 있다.

### 다운스트림 client 구조

- `M-ADP-PROJECT` 스타일의 client/config/dependency 구조가 반영되어 있다.
- `project`, `application`, `monitoring`, `user` client가 분리되어 있다.
- fake/real client 선택 구조가 구현되어 있다.
- dispatcher가 operation id 기준으로 적절한 client를 호출한다.

### 연결 완료된 기능 범위

다음 계열은 현재 ChatOps 실행 경로에 연결되어 있다.

- project command
  - create
  - update_name
  - update_resource
  - delete
  - add_member
  - remove_member
  - transfer_ownership
- project query
  - get
  - get_resource_limit
  - check_available
  - check_owner
  - list_members
  - list_projects
- application command
  - create_apps
  - delete_apps
  - patch_apps_resources
  - patch_apps_github
- application query
  - get_apps
  - get_apps_details
  - get_apps_logs
  - get_apps_status
- monitoring query
  - get_app_deployment_traffic
- user lookup
  - nickname 기반 profile lookup

### 테스트와 검증

- 자동 테스트가 통과하고 있다.
  - 현재 기준: `128 passed`
- fake downstream 기반 로컬 HTTP 검증을 반복적으로 수행했다.
- project real downstream 기준 end-to-end 검증을 수행한 이력이 있다.
- application create real downstream 기준 end-to-end 검증을 수행한 이력이 있다.

## 아직 100%가 아닌 이유

현재 백엔드는 구조적으로는 상당히 완성됐지만, 아래 항목이 닫히지 않아 100%라고 보기는 어렵다.

### real downstream 검증이 전체 범위를 덮지 못함

- project는 real 서버 기준 주요 흐름을 검증했지만, 모든 project query/command 조합을 real 기준으로 닫지는 못했다.
- application은 create 중심 검증은 했지만, delete/resource/github/status/logs/details까지 real 기준으로 모두 닫지 못했다.
- monitoring은 코드 연결은 되어 있지만 real downstream end-to-end 검증이 아직 부족하다.
- user lookup도 real user service 기준 검증이 충분하지 않다.

### 운영성 항목이 아직 부족함

- 승인 만료(`approval_expired`) 정책이 설계 수준 대비 충분히 닫히지 않았다.
- 장시간 연결/재연결 기준의 SSE 운영 검증이 부족하다.
- structured logging, metrics, trace 같은 운영 관측성이 충분히 정리되지 않았다.
- retry/timeout/backoff 정책이 operation별로 명확히 닫히지 않았다.

### 예외 시나리오를 더 닫아야 함

- downstream `401/403/404/409/422/5xx`별 사용자 메시지와 상태 전이가 전 operation에서 완전히 일관되지는 않다.
- approval 이후 부분 실패, 재시도, 중복 실행 방지 시나리오를 더 명확히 검증해야 한다.
- `Last-Event-ID` 기준 replay를 운영 수준에서 더 검증해야 한다.

## 100% 도달을 위한 남은 작업

### 1. real downstream E2E 매트릭스 완성

다음 조합을 real 환경 기준으로 모두 검증해야 한다.

- project
  - 생성
  - 이름 변경
  - 리소스 변경
  - 삭제
  - 멤버 추가
  - 멤버 제거
  - 소유권 이전
  - 상세/리소스/멤버/소유자/가능 여부 조회
- application
  - 생성
  - 삭제
  - 리소스 변경
  - GitHub 연결 변경
  - 목록/상태/로그/상세 조회
- monitoring
  - 앱 트래픽 조회
- user
  - nickname -> user_id lookup

완료 기준:
- fake가 아니라 실제 서버 호출로 검증한다.
- 성공/실패/권한 오류까지 확인한다.
- 검증 결과를 체크리스트로 남긴다.

### 2. 승인 흐름 운영 마감

- `approval_expired` 도입 여부와 TTL 동작을 실제로 구현/검증한다.
- 만료된 요청 재승인 시 `409`를 반환하는지 검증한다.
- 승인 후 중복 실행 방지를 명확히 검증한다.
- `reject`, `cancel`, `failed` 상태 전이를 실제 checkpoint resume 흐름에서 검증한다.

완료 기준:
- 승인 관련 모든 상태 전이가 테스트와 real smoke로 닫힌다.

### 3. SSE 운영 검증 마감

- `Last-Event-ID` replay를 request 전체 라이프사이클에서 검증한다.
- 연결 끊김 후 재연결 시 이벤트가 누락되지 않는지 확인한다.
- pending approval -> approve -> completed 전 구간에서 sequence 정합성을 확인한다.

완료 기준:
- SSE가 단순 동작 수준이 아니라 재연결/복구까지 포함해 검증된다.

### 4. 에러 표준화 마감

- project/application/monitoring/user client에서 오류 매핑 기준을 통일한다.
- `400/401/403/404/409/422/5xx/timeout`별 사용자 메시지를 확정한다.
- graph 상태(`failed`, `rejected`, `input_required`)와 사용자 메시지의 관계를 표로 고정한다.

완료 기준:
- operation마다 다른 예외 처리 편차가 없어야 한다.

### 5. 관측성과 운영 설정 정리

- `request_id`, `session_id`, `user_id` 중심 structured logging 추가
- downstream call trace와 latency metric 추가
- `.env.example`와 운영 설정 문서 정리
- fake/real client 전환 규칙 문서화

완료 기준:
- 배포 후 문제를 추적할 최소 운영 데이터가 남는다.

## 구현 순서

### 1순위

- real downstream E2E 전수 검증
- approval_expired + 승인 상태 예외 처리 마감
- SSE replay 운영 검증

### 2순위

- 에러 표준화 마감
- observability 추가
- 설정/운영 문서 정리

### 3순위

- smoke 스크립트 자동화
- 배포 전 체크리스트 문서화

## 완료 기준

다음 조건을 모두 만족하면 백엔드 오케스트레이션 100%로 본다.

- 설계된 API와 상태 전이가 모두 구현되어 있다.
- registry에 노출된 기능이 실제 실행 경로와 일치한다.
- project/application/monitoring/user real downstream E2E가 완료되었다.
- 승인, 재개, 만료, 실패, replay가 모두 검증되었다.
- 운영에 필요한 로그/설정/예외 기준이 문서화되어 있다.
