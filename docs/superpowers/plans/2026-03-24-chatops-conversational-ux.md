# ChatOps 대화형 UX 구현 계획

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 ChatOps를 실제 LLM처럼 느끼도록, 내부 상태 중심 응답을 `assistant_message` 중심의 대화형 UX로 바꾼다.

**Architecture:** 기존 `request` 상태 머신과 LangGraph 흐름은 유지하고, API 응답과 그래프 노드가 생성하는 사용자용 메시지 계층만 재구성한다. 부족한 정보 수집, 승인 질문, 실행 결과를 모두 대화형 문장으로 통일하고, 내부 API 이름과 내부 ID 노출을 차단한다.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic v2, LangGraph, SQLAlchemy, pytest

---

## 파일 구조

- Modify: `src/chatops/schemas/requests.py`
  - 사용자에게 보여줄 응답 필드 정의
- Modify: `src/chatops/api/routers/requests.py`
  - 응답 직렬화 시 `assistant_message` 제공
- Modify: `src/chatops/graph/nodes.py`
  - 상태별 사용자 메시지 생성 규칙 정리
- Modify: `src/chatops/services/llm.py`
  - inquiry/query 결과 문구가 내부 operation id를 노출하지 않도록 정리
- Modify: `tests/test_api_requests.py`
  - API 응답 스키마와 대화형 메시지 검증
- Modify: `tests/test_graph_service.py`
  - `input_required`, `pending_approval`, `completed`, `failed`의 메시지 검증

## Chunk 1: 응답 계약 정리

### Task 1: 사용자 표시용 응답 필드 추가

**Files:**
- Modify: `src/chatops/schemas/requests.py`
- Modify: `src/chatops/api/routers/requests.py`
- Test: `tests/test_api_requests.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`RequestResponse`에 사용자용 표시 필드가 없다는 점을 검증하는 테스트를 추가한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `./.venv/bin/python -m pytest tests/test_api_requests.py -q`
Expected: `assistant_message`가 없거나 기대 메시지와 달라서 FAIL

- [ ] **Step 3: 최소 구현 작성**

- `RequestResponse`에 `assistant_message` 필드를 추가한다.
- 라우터 응답 생성 시 `final_response`를 그대로 `assistant_message`로 복사한다.

- [ ] **Step 4: 테스트가 통과하는지 확인**

Run: `./.venv/bin/python -m pytest tests/test_api_requests.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/chatops/schemas/requests.py src/chatops/api/routers/requests.py tests/test_api_requests.py
git commit -m "feat(requests): 대화형 응답 필드를 추가한다"
```

## Chunk 2: 상태별 대화형 문구 통일

### Task 2: `input_required` 질문 문구를 대화형으로 정리

**Files:**
- Modify: `src/chatops/graph/nodes.py`
- Test: `tests/test_graph_service.py`

- [ ] **Step 1: 실패하는 테스트 작성**

부족한 값이 있을 때 응답이 “한 번에 필요한 항목을 모두 묻는 문장”인지 검증하는 테스트를 추가한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `./.venv/bin/python -m pytest tests/test_graph_service.py -q`
Expected: 현재 문구와 달라서 FAIL

- [ ] **Step 3: 최소 구현 작성**

- `_format_missing_input_response()`를 다음 원칙으로 수정한다.
  - 첫 줄은 항상 자연어 질문
  - 내부 필드명 대신 사용자 표현 사용
  - 필요한 항목은 한 번에 모두 제시

예:
- `프로젝트를 만들려면 아래 정보가 더 필요합니다. 프로젝트 이름, CPU, 메모리, 디스크를 알려주세요.`

- [ ] **Step 4: 테스트가 통과하는지 확인**

Run: `./.venv/bin/python -m pytest tests/test_graph_service.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/chatops/graph/nodes.py tests/test_graph_service.py
git commit -m "feat(graph): 부족한 정보 질문을 대화형으로 정리한다"
```

### Task 3: `pending_approval` 문구를 승인 질문형으로 정리

**Files:**
- Modify: `src/chatops/graph/nodes.py`
- Test: `tests/test_graph_service.py`

- [ ] **Step 1: 실패하는 테스트 작성**

승인 대기 문구가 내부 API명이 아니라 사용자 계획 설명 + 승인 질문인지 검증하는 테스트를 추가한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `./.venv/bin/python -m pytest tests/test_graph_service.py -q`
Expected: 현재 계획 문구와 달라서 FAIL

- [ ] **Step 3: 최소 구현 작성**

- `_build_command_plan()`을 사용자용 문장으로 통일한다.
- 마지막 줄은 항상 `실행할까요?`
- 내부 operation id가 포함되지 않도록 한다.

- [ ] **Step 4: 테스트가 통과하는지 확인**

Run: `./.venv/bin/python -m pytest tests/test_graph_service.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/chatops/graph/nodes.py tests/test_graph_service.py
git commit -m "feat(graph): 승인 질문 문구를 대화형으로 정리한다"
```

## Chunk 3: 완료/실패 응답 정리

### Task 4: 성공/실패 결과를 사용자 문장으로 통일

**Files:**
- Modify: `src/chatops/graph/nodes.py`
- Modify: `src/chatops/services/llm.py`
- Test: `tests/test_graph_service.py`
- Test: `tests/test_api_requests.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`completed`, `failed` 응답이 내부 API명 없이 사용자 문장인지 검증하는 테스트를 추가한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `./.venv/bin/python -m pytest tests/test_graph_service.py tests/test_api_requests.py -q`
Expected: 현재 `명령 실행 응답: project.create` 같은 문구 때문에 FAIL

- [ ] **Step 3: 최소 구현 작성**

- `respond_command()`를 operation-aware 사용자 문장으로 바꾼다.
- query/inquiry fallback도 내부 capability 이름 없이 응답하도록 정리한다.

예:
- 성공: `프로젝트를 생성했습니다.`
- 실패: `프로젝트 생성에 실패했습니다. 입력값을 다시 확인해주세요.`

- [ ] **Step 4: 테스트가 통과하는지 확인**

Run: `./.venv/bin/python -m pytest tests/test_graph_service.py tests/test_api_requests.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/chatops/graph/nodes.py src/chatops/services/llm.py tests/test_graph_service.py tests/test_api_requests.py
git commit -m "feat(ux): 완료 및 실패 응답을 사용자 문장으로 통일한다"
```

## Chunk 4: 최종 검증

### Task 5: 전체 회귀 테스트와 로컬 대화 흐름 확인

**Files:**
- Modify: 없음
- Test: 전체 테스트, 로컬 HTTP 수동 검증

- [ ] **Step 1: 전체 자동 테스트 실행**

Run: `./.venv/bin/python -m pytest tests -q`
Expected: 모든 테스트 PASS

- [ ] **Step 2: 로컬 HTTP 대화 흐름 검증**

아래 흐름을 실제로 확인한다.

1. `프로젝트 하나 만들어줘`
2. `프로젝트 이름, CPU, 메모리, 디스크를 알려주세요`
3. `이름은 demo고 cpu는 1, 메모리는 1, 디스크는 10이야`
4. `프로젝트 이름 demo, CPU 1, 메모리 1GB, 디스크 10GB로 생성할게요. 실행할까요?`
5. 승인
6. `프로젝트를 생성했습니다.`

- [ ] **Step 3: 검증 결과 정리**

성공한 응답 예시를 문서나 캡처용 텍스트로 남긴다.

- [ ] **Step 4: 커밋**

```bash
git add .
git commit -m "feat(ux): chatops를 대화형 응답 중심으로 정리한다"
```

---

Plan complete and saved to `docs/superpowers/plans/2026-03-24-chatops-conversational-ux.md`. Ready to execute?
