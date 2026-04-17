# Conversational Command Response Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 명령 실행 응답을 보고서형 문자열에서 대화형 안내로 전환하고, 생성 결과의 핵심 정보(무엇이 생성됐는지/상태/접속 정보)를 자연스럽게 전달한다.

**Architecture:** `CommandMessageBuilder`를 단일 응답 생성 진입점으로 유지하고, 구조화 데이터(`result.result.data`)를 operation별 템플릿에 바인딩한다. `WorkflowNodes.respond_command`는 단일/멀티스텝 모두 builder를 통해 최종 문장을 생성하도록 통일한다. 테스트는 builder 단위 + graph 통합으로 고정해 회귀를 방지한다.

**Tech Stack:** Python 3.12, pytest, LangGraph workflow nodes, dataclass 기반 서비스 구조

---

## File Structure

- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/graph/command_message_builder.py`
  - command 성공/실패 응답 템플릿과 상세 정보 조합 로직
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/graph/nodes.py`
  - 단일/멀티스텝 command 최종 응답 생성 경로
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_command_message_builder.py`
  - 대화형 문장/상세 정보 포함 여부 단위 테스트
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_graph_service.py`
  - 실제 GraphService 결과가 대화형 형태인지 통합 검증
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_verifier_control_loop.py`
  - retry/success 경로 최종 문장 검증
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_multistep.py`
  - 멀티스텝 응답이 단계별 대화형 문장을 유지하는지 검증

## Chunk 1: Message Contract Baseline

### Task 1: 대화형 응답 계약 테스트 먼저 고정

**Files:**
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_command_message_builder.py`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_graph_service.py`
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_verifier_control_loop.py`

- [ ] **Step 1: 실패 테스트 작성 (대화형/상세정보 계약)**

```python
# builder 단위
assert "프로젝트를 생성했습니다." in message
assert "프로젝트 이름" in message
assert "현재 상태" in message or "접속" in message

# graph 통합
assert "생성했습니다" in result.final_response
assert "실행 결과" in result.final_response
```

- [ ] **Step 2: 실패 확인**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_command_message_builder.py tests/test_graph_service.py tests/test_verifier_control_loop.py -q`
Expected: FAIL (기존 고정 문자열/포맷 불일치)

- [ ] **Step 3: 테스트 커밋**

```bash
git add tests/test_command_message_builder.py tests/test_graph_service.py tests/test_verifier_control_loop.py
git commit -m "test: define conversational command response contract"
```

## Chunk 2: Builder Implementation

### Task 2: operation별 대화형 템플릿 + 상세 정보 추출 구현

**Files:**
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/graph/command_message_builder.py`
- Test: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_command_message_builder.py`

- [ ] **Step 1: 최소 구현 (단위테스트 통과 목적)**

```python
def build_command_success_message(...):
    headline = ...
    details = _build_success_details(...)
    return "\n".join([...]) if details else f"{headline} {summary}".strip()
```

- [ ] **Step 2: operation별 상세 필드 매핑 구현**

```python
if operation_id == "project.create":
    # name, id, role, limits
if operation_id == "application.create_apps":
    # app name/id/status/resources/access_url|endpoint|port
```

- [ ] **Step 3: 단위 테스트 실행**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_command_message_builder.py -q`
Expected: PASS

- [ ] **Step 4: 구현 커밋**

```bash
git add src/chatops/graph/command_message_builder.py tests/test_command_message_builder.py
git commit -m "feat: add conversational success messages with resource details"
```

## Chunk 3: Workflow Integration

### Task 3: 단일/멀티스텝 최종 응답 경로 통일

**Files:**
- Modify: `/Users/jjm/Desktop/M-ADP-ChatOps/src/chatops/graph/nodes.py`
- Test: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_multistep.py`
- Test: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_graph_service.py`
- Test: `/Users/jjm/Desktop/M-ADP-ChatOps/tests/test_verifier_control_loop.py`

- [ ] **Step 1: `respond_command`에서 builder 단일 경로 사용**

```python
step_message = builder.build_command_success_message(step_op, step_summary, step_result)
final_response = builder.build_command_success_message(operation_id, summary, result)
```

- [ ] **Step 2: 멀티스텝 출력 가독성 정리**

```python
final_response = f"{n}개 작업 완료\n1) ...\n2) ..."
```

- [ ] **Step 3: 통합 테스트 실행**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_multistep.py tests/test_graph_service.py tests/test_verifier_control_loop.py -q`
Expected: PASS

- [ ] **Step 4: 구현 커밋**

```bash
git add src/chatops/graph/nodes.py tests/test_multistep.py tests/test_graph_service.py tests/test_verifier_control_loop.py
git commit -m "feat: unify conversational command responses for single and multi-step flows"
```

## Chunk 4: Final Verification

### Task 4: 전체 관련 회귀 검증

**Files:**
- Verify only

- [ ] **Step 1: 핵심 스위트 실행**

Run: `PYTHONPATH=. .venv/bin/pytest tests/test_command_message_builder.py tests/test_multistep.py tests/test_graph_service.py tests/test_verifier_control_loop.py tests/test_parameter_resolver.py tests/test_follow_up_interpreter.py -q`
Expected: PASS

- [ ] **Step 2: 변경 파일 점검**

Run: `git status --short`
Expected: 계획된 파일만 변경되어 있음

- [ ] **Step 3: 최종 커밋**

```bash
git add src/chatops/graph/command_message_builder.py src/chatops/graph/nodes.py tests/test_command_message_builder.py tests/test_multistep.py tests/test_graph_service.py tests/test_verifier_control_loop.py
git commit -m "feat: improve conversational command response UX"
```
