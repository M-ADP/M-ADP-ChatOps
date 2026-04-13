# ChatOps AI 고도화 — UX 품질 수정 계획

> 작성일: 2026-04-13 | 대상 브랜치: dev-0.1.6 (1343e97)

---

## 수정 대상 요약

| # | 문제 | 영향도 | 대상 파일 |
|---|------|--------|----------|
| 1 | 분류 가드레일 키워드 충돌 | **Critical** | `services/llm.py` |
| 2 | Planner fallback heuristic이 registry를 사용하지 않음 | Medium | `graph/planner_service.py` |
| 3 | Specialist가 메타데이터만 반환 | Medium | `graph/specialists/*.py`, `graph/specialist_router.py` |
| 4 | Verifier에 실행 컨텍스트 부재 | Medium | `graph/verifier_service.py`, `services/llm.py` |
| 5 | 다중 Step Plan 미실행 | Low | `graph/workflow.py`, `graph/nodes.py` |

---

## Fix 1: 분류 가드레일 키워드 충돌 (Critical)

### 현재 문제

`services/llm.py`의 `_apply_classification_guardrails`가 LLM 분류 결과를 키워드로 **무조건 덮어쓴다.**

```python
# 현재 로직: INQUIRY → COMMAND → QUERY 순서로 먼저 매칭된 것이 이긴다
if any(marker in normalized for marker in INQUIRY_MARKERS):
    forced_type = "inquiry"
elif any(marker in normalized for marker in COMMAND_MARKERS):
    forced_type = "command"
elif any(marker in normalized for marker in QUERY_MARKERS):
    forced_type = "query"
```

#### 오분류 시나리오

| 사용자 입력 | LLM 판단 | 가드레일 결과 | 정답 |
|------------|---------|-------------|------|
| "삭제 방법 알려줘" | command | **inquiry** (방법 먼저 매칭) | inquiry |
| "프로젝트 목록 생성해줘" | command | **command** (생성 매칭) | command (우연히 정답) |
| "상태 변경해줘" | command | **command** (변경 매칭) | command (우연히 정답) |
| "어떻게 삭제해?" | command | **inquiry** (어떻게 먼저 매칭) | inquiry |
| "앱 상태 확인하고 문제 있으면 재시작" | query+command | **command** (재시작 매칭) | 분리 필요 |

핵심: INQUIRY_MARKERS가 항상 먼저 체크되므로, "방법/어떻게/설명" + 액션 키워드 조합에서 inquiry로 강제된다.
이것이 LLM과 일치하면 괜찮지만, **LLM이 맞는데 가드레일이 틀리는 경우**가 문제다.

### 수정 방안

#### 1단계: 가드레일을 "보조" 역할로 전환

`_apply_classification_guardrails`를 **LLM 신뢰도 기반 조건부 적용**으로 변경한다.

```python
def _apply_classification_guardrails(
    self,
    message_text: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    confidence = float(result.get("classification_confidence", 0.0))
    
    # LLM 신뢰도가 높으면 가드레일 적용하지 않음
    if confidence >= 0.85:
        return result
    
    normalized = message_text.lower()
    keyword_signal = self._detect_keyword_signal(normalized)
    
    # LLM 신뢰도가 낮고, 키워드 신호가 명확할 때만 보정
    if keyword_signal is None:
        return result
    
    signal_type, signal_strength = keyword_signal
    
    # 키워드 신호와 LLM 결과가 같으면 신뢰도만 보강
    if signal_type == result["request_type"]:
        result = dict(result)
        result["classification_confidence"] = max(confidence, 0.9)
        return result
    
    # 키워드 신호와 LLM 결과가 다르고, 키워드 신호가 강할 때만 덮어쓰기
    if signal_strength == "strong" and confidence < 0.6:
        return {
            **result,
            "request_type": signal_type,
            "classification_reason": f"가드레일 보정: {signal_type} (LLM confidence={confidence:.2f})",
            "classification_confidence": 0.75,
        }
    
    return result
```

#### 2단계: 복합 키워드 패턴 감지

단일 키워드가 아니라 **복합 패턴**을 감지한다.

```python
# 복합 패턴 (inquiry + action 조합)
INQUIRY_ACTION_PATTERNS = [
    # "X 방법", "X 어떻게", "X 설명" → inquiry
    re.compile(r"(삭제|생성|수정|변경|배포|실행)\s*(방법|어떻게|가이드|설명|사용법)"),
    re.compile(r"(방법|어떻게|가이드|설명|사용법)\s*(을|를)?\s*(알려|보여|설명)"),
]

def _detect_keyword_signal(self, normalized: str) -> tuple[str, str] | None:
    """키워드 기반 분류 신호를 반환한다. (type, strength)"""
    
    # 1. 복합 패턴 우선 체크 (strong)
    for pattern in INQUIRY_ACTION_PATTERNS:
        if pattern.search(normalized):
            return ("inquiry", "strong")
    
    # 2. 개별 키워드 카운팅
    inquiry_count = sum(1 for m in INQUIRY_MARKERS if m in normalized)
    command_count = sum(1 for m in COMMAND_MARKERS if m in normalized)
    query_count = sum(1 for m in QUERY_MARKERS if m in normalized)
    
    # 3. 단일 카테고리만 매칭되면 strong
    counts = {"inquiry": inquiry_count, "command": command_count, "query": query_count}
    nonzero = {k: v for k, v in counts.items() if v > 0}
    
    if len(nonzero) == 1:
        signal_type = next(iter(nonzero))
        return (signal_type, "strong")
    
    if len(nonzero) >= 2:
        # 여러 카테고리 키워드가 섞여있으면 weak 신호
        dominant = max(nonzero, key=nonzero.get)
        return (dominant, "weak")
    
    return None
```

#### 3단계: fallback 분류에도 같은 로직 적용

`_fallback_classification`에서도 복합 패턴을 먼저 체크하도록 수정한다.

```python
def _fallback_classification(self, message_text: str) -> dict[str, Any]:
    normalized = message_text.lower()
    
    # 복합 패턴 우선
    for pattern in INQUIRY_ACTION_PATTERNS:
        if pattern.search(normalized):
            return self._build_classification("inquiry", "answer_inquiry", "복합 패턴 감지", 0.8)
    
    # 개별 키워드 (기존 로직)
    signal = self._detect_keyword_signal(normalized)
    if signal is not None:
        signal_type, _ = signal
        # ... 기존 매핑 로직
```

### 테스트 케이스

```python
# tests/test_classification_guardrail.py

@pytest.mark.parametrize("message, expected_type", [
    ("삭제 방법 알려줘", "inquiry"),           # 복합 패턴: 액션+inquiry
    ("프로젝트 어떻게 만들어?", "inquiry"),      # 복합 패턴: 어떻게+액션
    ("my-app 앱 삭제해줘", "command"),          # 순수 command
    ("프로젝트 목록 보여줘", "query"),           # 순수 query
    ("앱 상태 확인해줘", "query"),              # 순수 query
    ("프로젝트 생성해줘", "command"),           # 순수 command
    ("앱 로그 보여주고 문제 있으면 재시작", "query"),  # 복합 → LLM 판단 우선
])
def test_guardrail_cases(message, expected_type):
    ...
```

### 파일 변경 목록

| 파일 | 변경 내용 |
|------|----------|
| `services/llm.py` | `_apply_classification_guardrails` 전면 교체, `_detect_keyword_signal` 추가, `INQUIRY_ACTION_PATTERNS` 추가 |
| `tests/test_llm_classification.py` | 복합 패턴 테스트 케이스 추가 |

---

## Fix 2: Planner Fallback이 Registry를 사용하도록 변경 (Medium)

### 현재 문제

`graph/planner_service.py`의 `_heuristic_candidate_operation_ids`가 독립적인 키워드 매핑을 사용한다.

```python
# 현재: 하드코딩된 매핑 (10개 미만)
if "트래픽" in normalized:
    return ["monitoring.get_app_deployment_traffic"]
if "상태" in normalized:
    return ["application.get_apps_status"]
```

하지만 실제 operation 선택은 `registry_service.find_scored_candidates()`가 300줄 이상의 정교한 스코어링으로 처리한다. **Planner heuristic이 registry와 다른 결과를 낼 수 있다.**

> 참고: planner의 candidate가 실제 실행 경로에는 영향 없음 (query_planner/command_planner가 별도로 registry 호출).
> 하지만 `plan_object`에 잘못된 specialist/operation이 기록되면 session_summary와 eval 지표에 부정확한 데이터가 쌓인다.

### 수정 방안

`PlannerService`에 `registry_service`를 주입받아 `find_scored_candidates`를 호출한다.

```python
# graph/planner_service.py

@dataclass(frozen=True)
class PlannerService:
    llm_service: Any
    registry_service: Any  # 이미 주입되어 있음

    def build(self, *, message_text: str, request_type: str) -> dict[str, object] | None:
        if request_type not in {"query", "command"}:
            return None
        
        # LLM plan 시도
        candidate_operation_ids = self._registry_candidate_operation_ids(
            message_text=message_text,
            request_type=request_type,
        )
        if hasattr(self.llm_service, "build_plan_object"):
            plan = self.llm_service.build_plan_object(
                message_text=message_text,
                request_type=request_type,
                candidate_operation_ids=candidate_operation_ids,
            )
            if isinstance(plan, dict):
                return plan
        
        return self._fallback_plan(
            message_text=message_text,
            request_type=request_type,
            candidate_operation_ids=candidate_operation_ids,
        )

    def _registry_candidate_operation_ids(
        self,
        *,
        message_text: str,
        request_type: str,
    ) -> list[str]:
        """registry의 스코어링을 사용하여 후보를 뽑는다."""
        usable_in = request_type  # "query" or "command"
        scored = self.registry_service.find_scored_candidates(
            message_text, usable_in=usable_in, limit=3,
        )
        if scored:
            return [sc.entry.id for sc in scored]
        
        # registry도 못 찾으면 기존 heuristic fallback
        return self._heuristic_candidate_operation_ids(
            message_text=message_text,
            request_type=request_type,
        )
```

**기존 `_heuristic_candidate_operation_ids`는 삭제하지 않고** registry 결과가 없을 때의 최종 fallback으로 유지한다.

### 파일 변경 목록

| 파일 | 변경 내용 |
|------|----------|
| `graph/planner_service.py` | `_registry_candidate_operation_ids` 추가, `build`에서 호출 순서 변경 |
| `tests/test_planner_service.py` | registry 연동 테스트 추가 |

---

## Fix 3: Specialist에 도메인별 실행 로직 추가 (Medium)

### 현재 문제

3개 Specialist (application, monitoring, project)가 전부 빈 클래스다.

```python
class ApplicationSpecialist(BaseSpecialist):
    def __init__(self) -> None:
        super().__init__(name="application")
```

`BaseSpecialist.describe()`는 이름만 반환한다. Specialist가 실행 경로에 **아무 영향도 주지 않는다.**

### 수정 방안

Specialist에 3가지 역할을 부여한다.

#### 역할 1: 도메인별 입력 검증 (`validate_inputs`)

```python
# graph/specialists/base.py

@dataclass(frozen=True)
class BaseSpecialist:
    name: str

    def describe(self, *, operation_id, resolved_inputs, missing_inputs) -> dict[str, object]:
        # 기존 로직 유지
        ...

    def validate_inputs(
        self,
        *,
        operation_id: str | None,
        resolved_inputs: dict[str, object] | None,
    ) -> list[str]:
        """도메인별 입력 유효성 검사. 문제가 있으면 경고 메시지 리스트 반환."""
        return []

    def format_result(
        self,
        *,
        operation_id: str | None,
        raw_result: dict[str, object],
    ) -> dict[str, object]:
        """도메인별 결과 포맷팅. 기본은 pass-through."""
        return raw_result

    def suggest_retry_strategy(
        self,
        *,
        operation_id: str | None,
        error_result: dict[str, object],
    ) -> str | None:
        """도메인별 재시도 전략 제안. None이면 기본 정책 사용."""
        return None
```

#### 역할 2: Application Specialist 구현

```python
# graph/specialists/application.py

class ApplicationSpecialist(BaseSpecialist):
    def __init__(self) -> None:
        super().__init__(name="application")

    def validate_inputs(self, *, operation_id, resolved_inputs) -> list[str]:
        warnings = []
        inputs = resolved_inputs or {}
        references = inputs.get("references", {})
        
        if operation_id == "application.create_apps":
            app_name = references.get("application_name", "")
            if app_name and not re.match(r"^[a-z][a-z0-9-]*$", str(app_name)):
                warnings.append(
                    f"앱 이름 '{app_name}'에 허용되지 않는 문자가 있습니다. "
                    "소문자, 숫자, 하이픈만 사용 가능합니다."
                )
        
        if operation_id == "application.patch_apps_resources":
            body = inputs.get("body", {})
            cpu = body.get("cpu")
            memory = body.get("memory")
            if cpu is not None and isinstance(cpu, (int, float)) and cpu > 8:
                warnings.append(f"CPU {cpu}코어는 상한을 초과할 수 있습니다.")
            if memory is not None and isinstance(memory, (int, float)) and memory > 16384:
                warnings.append(f"메모리 {memory}MB는 상한을 초과할 수 있습니다.")
        
        return warnings

    def format_result(self, *, operation_id, raw_result) -> dict[str, object]:
        if operation_id == "application.get_apps_status":
            data = raw_result.get("data") or raw_result.get("result") or {}
            if isinstance(data, dict):
                status = data.get("status", "unknown")
                raw_result = dict(raw_result)
                raw_result["formatted_summary"] = f"앱 상태: {status}"
        return raw_result

    def suggest_retry_strategy(self, *, operation_id, error_result) -> str | None:
        status_code = error_result.get("status_code", 0)
        if operation_id in ("application.get_apps_logs",) and status_code == 504:
            return "앱 로그 조회가 타임아웃됐습니다. 시간 범위를 줄여 다시 시도합니다."
        return None
```

#### 역할 3: Project / Monitoring Specialist도 동일하게 확장

```python
# graph/specialists/project.py

class ProjectSpecialist(BaseSpecialist):
    def __init__(self) -> None:
        super().__init__(name="project")

    def validate_inputs(self, *, operation_id, resolved_inputs) -> list[str]:
        warnings = []
        inputs = resolved_inputs or {}
        references = inputs.get("references", {})
        
        if operation_id == "project.create":
            name = references.get("project_name", "")
            if name and len(str(name)) < 2:
                warnings.append("프로젝트 이름이 너무 짧습니다. 2자 이상 입력해주세요.")
        
        if operation_id == "project.transfer_ownership":
            target = references.get("target_nickname")
            if not target:
                warnings.append("소유권을 이전할 대상 사용자를 지정해주세요.")
        
        return warnings

    def suggest_retry_strategy(self, *, operation_id, error_result) -> str | None:
        status_code = error_result.get("status_code", 0)
        if status_code == 409:
            return "리소스 충돌이 발생했습니다. 최신 상태를 확인 후 다시 시도합니다."
        return None
```

```python
# graph/specialists/monitoring.py

class MonitoringSpecialist(BaseSpecialist):
    def __init__(self) -> None:
        super().__init__(name="monitoring")

    def format_result(self, *, operation_id, raw_result) -> dict[str, object]:
        if operation_id == "monitoring.get_app_deployment_traffic":
            data = raw_result.get("data") or raw_result.get("result") or {}
            if isinstance(data, dict) and "traffic" in data:
                raw_result = dict(raw_result)
                raw_result["formatted_summary"] = f"현재 트래픽: {data['traffic']}"
        return raw_result

    def suggest_retry_strategy(self, *, operation_id, error_result) -> str | None:
        status_code = error_result.get("status_code", 0)
        if status_code in (502, 503, 504):
            return "모니터링 서버 일시 장애입니다. 30초 후 재시도합니다."
        return None
```

#### Workflow에서 Specialist 호출 연결

`nodes.py`의 `prepare_query`와 `plan_command`에서 `validate_inputs` 호출을 추가한다.

```python
# nodes.py — prepare_query 수정

specialist = self.specialist_router.for_operation(selected_operation_id)
# 기존: describe만 호출
prepared["specialist_result"] = specialist.describe(...)

# 추가: 도메인 검증
input_warnings = specialist.validate_inputs(
    operation_id=selected_operation_id,
    resolved_inputs=prepared.get("resolved_inputs"),
)
if input_warnings:
    prepared["specialist_result"]["input_warnings"] = input_warnings
```

`execute_query`와 `execute_command`에서 `format_result` 호출을 추가한다.

```python
# nodes.py — execute_query 수정 (execute_command도 동일)

query_result = self._run_awaitable(...)

# 추가: 도메인별 결과 포맷팅
specialist = self.specialist_router.for_operation(operation_id)
query_result = specialist.format_result(
    operation_id=operation_id,
    raw_result=query_result,
)
```

`verify_query`와 `verify_command`에서 `suggest_retry_strategy` 호출을 추가한다.

```python
# nodes.py — verify_query 수정

verifier_decision = self.verifier_service.verify(...)

# 추가: specialist 재시도 전략 참조
if verifier_decision.get("decision") == "retry":
    specialist = self.specialist_router.for_operation(state.get("selected_operation_id"))
    retry_hint = specialist.suggest_retry_strategy(
        operation_id=state.get("selected_operation_id"),
        error_result=state.get("query_result") or {},
    )
    if retry_hint:
        verifier_decision = {**verifier_decision, "retry_hint": retry_hint}
```

### 파일 변경 목록

| 파일 | 변경 내용 |
|------|----------|
| `graph/specialists/base.py` | `validate_inputs`, `format_result`, `suggest_retry_strategy` 메서드 추가 |
| `graph/specialists/application.py` | 앱 이름 검증, 리소스 상한 검증, 로그 타임아웃 재시도 |
| `graph/specialists/project.py` | 프로젝트 이름 길이 검증, 소유권 이전 대상 검증, 409 충돌 재시도 |
| `graph/specialists/monitoring.py` | 트래픽 결과 포맷팅, 모니터링 서버 장애 재시도 |
| `graph/nodes.py` | `prepare_query`, `plan_command`, `execute_query`, `execute_command`, `verify_query`, `verify_command`에 specialist 호출 추가 |
| `tests/test_specialists.py` | 각 specialist의 validate/format/retry 테스트 |

---

## Fix 4: Verifier에 실행 컨텍스트 전달 (Medium)

### 현재 문제

#### 문제 A: Verifier가 status_code만 본다

```python
# verifier_service.py — 현재 로직
status_code = int(result.get("status_code", 200))
if result.get("success") is False:
    if status_code >= 500: return {"decision": "retry", ...}
    # ...
return {"decision": "success", ...}  # success=True면 무조건 성공
```

API가 `{"success": true, "data": []}` (빈 결과)를 반환해도 "성공"으로 판정한다.

#### 문제 B: LLM Verifier 프롬프트에 컨텍스트 없음

```python
# llm.py — 현재 프롬프트
"당신은 ChatOps verifier다. 실행 결과를 보고 success, retry, clarify, escalate, stop 중 하나를 고른다."
# execution_result만 전달, 어떤 작업이었는지 모름
```

### 수정 방안

#### 4-A: VerifierService에 의미론적 검증 추가

```python
# graph/verifier_service.py

@dataclass(frozen=True)
class VerifierService:
    llm_service: Any | None = None

    def verify(
        self,
        *,
        request_type: str,
        operation_id: str | None,
        execution_result: dict[str, Any] | None,
        message_text: str | None = None,       # 추가
        resolved_inputs: dict[str, Any] | None = None,  # 추가
    ) -> dict[str, object]:
        result = execution_result or {}
        
        # 1. LLM verifier (컨텍스트 포함)
        if hasattr(self.llm_service, "verify_execution"):
            decision = self.llm_service.verify_execution(
                execution_result=result,
                operation_id=operation_id,      # 추가
                message_text=message_text,       # 추가
            )
            if isinstance(decision, dict):
                return decision
        
        # 2. 의미론적 검증 (새로 추가)
        semantic_issue = self._check_semantic_quality(
            result=result,
            operation_id=operation_id,
            resolved_inputs=resolved_inputs,
        )
        if semantic_issue is not None:
            return semantic_issue
        
        # 3. 기존 status_code 기반 검증
        return self._status_code_based_verify(result)

    def _check_semantic_quality(
        self,
        *,
        result: dict[str, Any],
        operation_id: str | None,
        resolved_inputs: dict[str, Any] | None,
    ) -> dict[str, object] | None:
        """success=True여도 의미적으로 문제가 있는 경우를 감지한다."""
        
        if result.get("success") is not True:
            return None
        
        data = result.get("data") or result.get("result")
        
        # 케이스 1: 조회 결과가 빈 배열/빈 딕셔너리
        if isinstance(data, list) and len(data) == 0:
            return {
                "decision": "success",  # 에러는 아님
                "summary": "조회 결과가 없습니다.",
                "missing_inputs": [],
                "follow_up_action": "complete",
                "semantic_warning": "empty_result",
            }
        
        if isinstance(data, dict) and not data:
            return {
                "decision": "success",
                "summary": "조회 결과가 비어 있습니다.",
                "missing_inputs": [],
                "follow_up_action": "complete",
                "semantic_warning": "empty_result",
            }
        
        # 케이스 2: 예상 필드 누락 (operation별)
        if operation_id and isinstance(data, dict):
            expected_fields = self._expected_fields_for(operation_id)
            missing_fields = [f for f in expected_fields if f not in data]
            if missing_fields and len(missing_fields) >= len(expected_fields) * 0.5:
                return {
                    "decision": "clarify",
                    "summary": f"응답에 예상 필드가 누락되었습니다: {', '.join(missing_fields)}",
                    "missing_inputs": [],
                    "follow_up_action": "clarify",
                    "semantic_warning": "missing_expected_fields",
                }
        
        return None

    @staticmethod
    def _expected_fields_for(operation_id: str) -> list[str]:
        """operation별로 응답에 있어야 할 최소 필드를 정의한다."""
        EXPECTED = {
            "project.get": ["id", "name"],
            "project.list_projects": ["items"],
            "application.get_apps_status": ["status"],
            "application.get_apps": ["items"],
            "monitoring.get_app_deployment_traffic": ["traffic"],
        }
        return EXPECTED.get(operation_id, [])
    
    def _status_code_based_verify(self, result: dict[str, Any]) -> dict[str, object]:
        """기존 status_code 기반 검증 (변경 없음)."""
        # ... 기존 로직 그대로 유지
```

#### 4-B: LLM Verifier 프롬프트에 컨텍스트 추가

```python
# services/llm.py — verify_execution 수정

def verify_execution(
    self,
    execution_result: dict[str, Any],
    operation_id: str | None = None,    # 추가
    message_text: str | None = None,     # 추가
) -> dict[str, Any]:
    try:
        context_parts = []
        if operation_id:
            context_parts.append(f"실행된 작업: {operation_id}")
        if message_text:
            context_parts.append(f"사용자 요청: {message_text}")
        context = "\n".join(context_parts) if context_parts else "컨텍스트 없음"
        
        content = self._text_response(
            system_prompt=(
                "당신은 ChatOps verifier다. 실행 결과를 보고 "
                "success, retry, clarify, escalate, stop 중 하나를 고른다.\n"
                "판단 기준:\n"
                "- success: 결과가 요청 의도에 부합\n"
                "- retry: 일시적 오류 (5xx, timeout)\n"
                "- clarify: 결과가 비어있거나 요청과 불일치\n"
                "- escalate: 권한 문제 또는 위험한 상태 감지\n"
                "- stop: 복구 불가능한 오류\n"
                "JSON 객체만 반환하고 키는 decision, summary, "
                "missing_inputs, follow_up_action 을 사용한다."
            ),
            user_prompt=(
                f"{context}\n"
                f"execution_result: {json.dumps(execution_result, ensure_ascii=False)}"
            ),
        )
        # ... 기존 파싱 로직
```

#### 4-C: nodes.py에서 컨텍스트 전달

```python
# nodes.py — verify_query 수정

verifier_decision = self.verifier_service.verify(
    request_type="query",
    operation_id=state.get("selected_operation_id"),
    execution_result=state.get("query_result"),
    message_text=state.get("effective_message_text", state.get("message_text")),  # 추가
    resolved_inputs=state.get("resolved_inputs"),  # 추가
)
```

### 파일 변경 목록

| 파일 | 변경 내용 |
|------|----------|
| `graph/verifier_service.py` | `_check_semantic_quality`, `_expected_fields_for` 추가. `verify` 시그니처에 `message_text`, `resolved_inputs` 추가 |
| `services/llm.py` | `verify_execution` 프롬프트에 operation_id, message_text 추가. `LLMService` Protocol에 시그니처 변경 반영 |
| `graph/nodes.py` | `verify_query`, `verify_command`에서 message_text, resolved_inputs 전달 |
| `tests/test_verifier_service.py` | 빈 결과, 필드 누락 등 의미론적 검증 테스트 추가 |

---

## Fix 5: 다중 Step Plan 실행 지원 (Low — 향후)

### 현재 문제

Planner가 `candidate_steps`를 여러 개 생성해도 workflow에서 **첫 번째 step만 실행**한다.

```python
# 현재: query_planner/command_planner가 scored[0].entry만 사용
selected = scored[0].entry
```

### 수정 방안 (2단계)

#### Phase 1: Plan step 추적 (상태 관리만)

```python
# graph/state.py — 추가 필드

class GraphState(TypedDict, total=False):
    # ... 기존 필드
    current_step_index: int          # 현재 실행 중인 step 인덱스
    completed_steps: list[dict]      # 완료된 step 결과들
    total_steps: int                 # 전체 step 수
```

#### Phase 2: Workflow에 step 루프 추가

```python
# graph/workflow.py — 조건부 엣지 추가

graph.add_conditional_edges(
    "respond_command",
    lambda state: (
        "plan_next_step"
        if state.get("current_step_index", 0) < state.get("total_steps", 1) - 1
        else "complete"
    ),
    {
        "plan_next_step": "plan_command",  # 다음 step 계획
        "complete": END,
    },
)
```

> 이 수정은 현재 단일 step 동작에 영향을 주지 않는 **후방 호환** 방식으로 구현한다.
> `total_steps`가 1이면 기존과 동일하게 동작한다.

### 파일 변경 목록

| 파일 | 변경 내용 |
|------|----------|
| `graph/state.py` | `current_step_index`, `completed_steps`, `total_steps` 추가 |
| `graph/nodes.py` | `plan_command`에서 step index 증가 로직 |
| `graph/workflow.py` | step 루프 조건부 엣지 추가 |

---

## 구현 순서

```
Fix 1 (분류 가드레일)     ← 가장 큰 UX 영향, 먼저 수정
  ↓
Fix 4 (Verifier 컨텍스트)  ← Fix 1과 독립, 병렬 작업 가능
  ↓
Fix 2 (Planner registry)  ← 작업량 적음, 빠르게 적용
  ↓
Fix 3 (Specialist 로직)   ← 가장 큰 코드 변경, 충분한 테스트 필요
  ↓
Fix 5 (다중 Step)         ← 향후 과제, 설계만 선행
```

## 예상 작업량

| Fix | 예상 시간 | 신규 코드 | 테스트 |
|-----|----------|----------|--------|
| Fix 1 | 2-3h | ~80줄 | ~15 케이스 |
| Fix 2 | 1h | ~15줄 | ~5 케이스 |
| Fix 3 | 3-4h | ~150줄 | ~20 케이스 |
| Fix 4 | 2-3h | ~80줄 | ~15 케이스 |
| Fix 5 | 4-5h (설계 포함) | ~50줄 | ~10 케이스 |
| **합계** | **12-16h** | **~375줄** | **~65 케이스** |
