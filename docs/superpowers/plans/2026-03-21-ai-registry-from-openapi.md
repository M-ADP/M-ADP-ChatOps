# OpenAPI 기반 AI 레지스트리 구현 계획

> **에이전트 작업 규칙:** 이 계획을 구현할 때는 반드시 `superpowers:subagent-driven-development`(subagent 사용 가능 시) 또는 `superpowers:executing-plans`를 사용한다. 진행 상황은 체크박스(`- [ ]`)로 관리한다.

**목표:** 기존 `apis/*.yaml` OpenAPI 파일을 기반으로 AI가 사용할 수 있는 operation 단위 메타데이터 레이어를 만들고, 이를 안전하게 재생성할 수 있는 생성 스크립트를 구현한다.

**아키텍처:** 기존 OpenAPI 파일은 원본 소스로 유지하고, operation 단위로 분리된 별도 `ai_registry/` 레이어를 추가한다. 작은 Python 패키지가 OpenAPI를 파싱하고, operation을 정규화하며, 안전한 기본값을 추론해 AI 메타데이터 YAML 파일을 생성한다. 생성된 메타데이터는 LangGraph가 `read`와 `write`를 구분할 만큼의 구조를 제공하면서, 사람이 보강한 필드는 재생성 시 유지해야 한다.

**기술 스택:** Python 3.12+, PyYAML, pytest

---

## 청크 1: 생성기와 스키마

### 작업 1: Python 프로젝트 파일과 테스트 환경 준비

**파일:**
- Create: `requirements.txt`
- Create: `src/ai_registry/__init__.py`
- Create: `pytest.ini`
- Test: `tests/test_generator_cli.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from pathlib import Path



def test_generator_cli_module_exists() -> None:
    assert Path("src/ai_registry/__init__.py").exists()
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_generator_cli.py -v`
예상 결과: 패키지 파일이 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

`src/ai_registry/__init__.py`, `requirements.txt`, `pytest.ini` 생성

`requirements.txt`:

```text
PyYAML>=6.0
pytest>=8.0
```

`pytest.ini`:

```ini
[pytest]
pythonpath = src
```

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_generator_cli.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

### 작업 2: OpenAPI operation을 정규화된 모델로 파싱

**파일:**
- Create: `src/ai_registry/models.py`
- Create: `src/ai_registry/openapi_loader.py`
- Test: `tests/test_openapi_loader.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from pathlib import Path

from ai_registry.openapi_loader import load_operations



def test_load_operations_extracts_project_create() -> None:
    operations = load_operations(Path("apis/project.yaml"))
    project_create = next(op for op in operations if op.id == "project.create")

    assert project_create.method == "POST"
    assert project_create.path == "/projects"
    assert "X-User-Id" in project_create.required_headers
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_openapi_loader.py -v`
예상 결과: loader 모듈이 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

구현 항목:

- `src/ai_registry/models.py`에 `OpenAPIOperation` dataclass 추가
- `src/ai_registry/openapi_loader.py`에 `load_operations(path: Path) -> list[OpenAPIOperation]` 구현
- operation ID 정규화 규칙
  - `operationId`가 있으면 그것을 시작점으로 사용
  - 없으면 `method + path`에서 안정적인 slug 생성
  - `_endpoint_*_<method>` 같은 노이즈 suffix 제거
  - `create_project`, `list_projects`, `get_app_deployment_traffic` 같은 의미 있는 토큰 보존
  - 최종 canonical ID는 `<source_stem>.<semantic_slug>` 형식 사용
  - 파일명도 같은 canonical ID에 `.ai.yaml`을 붙여 사용
- 아래 필드 추출
  - `source_file`
  - `operation_id`
  - `path`
  - `method`
  - `summary`
  - `required_headers`
  - `required_inputs`

`required_inputs`는 아래 구조를 따른다.

```python
{
    "headers": [{"name": "X-User-Id", "required": True, "schema": {"type": "string"}}],
    "path": [{"name": "project_id", "required": True, "schema": {"type": "integer"}}],
    "query": [],
    "body": {
        "required": True,
        "content_type": "application/json",
        "schema_ref": "#/components/schemas/ProjectCreate",
    },
}
```

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_openapi_loader.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

### 작업 3: 안전한 기본값을 가진 AI 메타데이터 스캐폴드 생성

**파일:**
- Create: `src/ai_registry/scaffold.py`
- Create: `scripts/generate_ai_registry.py`
- Test: `tests/test_scaffold.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from pathlib import Path

from ai_registry.openapi_loader import load_operations
from ai_registry.scaffold import build_metadata



def test_build_metadata_marks_get_as_read_query() -> None:
    operations = load_operations(Path("apis/project.yaml"))
    list_projects = next(op for op in operations if op.method == "GET" and op.path == "/projects")
    metadata = build_metadata(list_projects)

    assert metadata["operation_kind"] == "read"
    assert metadata["usable_in"] == ["query"]
    assert metadata["requires_confirmation"] is False
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_scaffold.py -v`
예상 결과: scaffold builder가 아직 없어서 FAIL

- [ ] **단계 3: 최소 구현 작성**

`build_metadata(operation)` 구현 규칙:

- `GET` -> `operation_kind=read`, `usable_in=["query"]`, `requires_confirmation=false`, `risk_level=low`
- `POST`, `PATCH`, `PUT` -> `operation_kind=write` 또는 `action`, `usable_in=["command"]`, `requires_confirmation=true`
- `DELETE` -> `operation_kind=delete`, `usable_in=["command"]`, `requires_confirmation=true`, `risk_level=high`
- `capability` 기본값은 summary
- `when_to_use`, `when_not_to_use`, `side_effects`, `preconditions`, `missing_info_questions`, `response_interpretation`, `plan_template`, `examples`는 사람 보강을 위한 안전한 placeholder로 생성
- 재생성은 canonical ID 정렬 기준으로 deterministic 해야 함
- 재생성 시 자동 생성 필드는 덮어씀
- 기존 파일이 있으면 사람이 보강한 필드는 유지
- 오래된 파일은 기본값으로 삭제하지 않음

`scripts/generate_ai_registry.py` 구현:

- `apis/*.yaml` 스캔
- operation 로드
- operation별 `.ai.yaml` 파일을 `ai_registry/` 아래에 생성

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_scaffold.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

## 청크 2: 초기 레지스트리 생성

### 작업 4: 현재 API 기준 operation 단위 AI 메타데이터 파일 생성

**파일:**
- Create: `ai_registry/*.ai.yaml`
- Modify: `docs/superpowers/specs/2026-03-21-langgraph-orchestrator-design.md`
- Test: `tests/test_generator_cli.py`

- [ ] **단계 1: 실패하는 테스트 작성**

```python
from pathlib import Path
import subprocess
import sys



def test_generator_creates_operation_level_files(tmp_path) -> None:
    out_dir = tmp_path / "ai_registry"
    subprocess.run(
        [sys.executable, "scripts/generate_ai_registry.py", "--input-dir", "apis", "--output-dir", str(out_dir)],
        check=True,
    )

    generated = sorted(p.name for p in out_dir.glob("*.ai.yaml"))
    assert "project.create.ai.yaml" in generated
    assert "monitoring.get_app_deployment_traffic.ai.yaml" in generated
```

- [ ] **단계 2: 테스트가 실패하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_generator_cli.py -v`
예상 결과: CLI와 출력 생성이 완성되기 전까지 FAIL

- [ ] **단계 3: 최소 구현 작성**

CLI 동작을 마무리하고, 초기 메타데이터 파일을 `ai_registry/` 아래에 생성한다.

구현 과정에서 파일 경로나 필드명이 바뀌었다면 설계 문서도 그 변경분만 반영한다.

- [ ] **단계 4: 테스트가 통과하는지 확인**

실행: `.venv/bin/python -m pytest tests/test_generator_cli.py -v`
예상 결과: PASS

- [ ] **단계 5: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

## 청크 3: 최종 검증

### 작업 5: 생성 결과와 동작 검증

**파일:**
- Verify: `ai_registry/*.ai.yaml`
- Verify: `scripts/generate_ai_registry.py`
- Verify: `tests/*.py`

- [ ] **단계 1: 테스트 전체 실행**

실행: `.venv/bin/python -m pytest tests -v`
예상 결과: 모든 테스트 PASS

- [ ] **단계 2: 실제 프로젝트 파일로 생성기 실행**

실행: `.venv/bin/python scripts/generate_ai_registry.py --input-dir apis --output-dir ai_registry`
예상 결과: exit code 0, operation별 `.ai.yaml` 파일 생성 또는 갱신

- [ ] **단계 3: read 1개, write 1개 메타데이터 파일 점검**

점검 예시:

- `ai_registry/project.list_projects.ai.yaml`
- `ai_registry/project.create.ai.yaml`

확인 항목:

- `usable_in`
- `operation_kind`
- `requires_confirmation`
- `required_headers`
- `required_inputs`
- 사람이 보강한 필드 유지 여부

- [ ] **단계 4: 커밋**

저장소가 git으로 초기화되어 있지 않으므로 이 작업에서는 커밋을 생략한다.

---

계획 문서를 `docs/superpowers/plans/2026-03-21-ai-registry-from-openapi.md`에 저장했다. 필요하면 이 계획을 기준으로 다시 구현하거나 확장 작업을 진행한다.
