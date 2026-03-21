from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai_registry.models import OpenAPIOperation
from ai_registry.openapi_loader import load_operations


MANUAL_FIELDS = {
    "capability",
    "usable_in",
    "operation_kind",
    "when_to_use",
    "when_not_to_use",
    "requires_confirmation",
    "risk_level",
    "side_effects",
    "preconditions",
    "missing_info_questions",
    "response_interpretation",
    "plan_template",
    "examples",
}


def infer_operation_kind(method: str) -> tuple[str, list[str], bool, str]:
    if method == "GET":
        return "read", ["query"], False, "low"
    if method == "DELETE":
        return "delete", ["command"], True, "high"
    return "write", ["command"], True, "medium"


def _collect_missing_info_questions(required_inputs: dict[str, Any]) -> list[str]:
    questions: list[str] = []
    for location in ("headers", "path", "query"):
        for entry in required_inputs.get(location, []):
            questions.append(f"{entry['name']} 값을 확인해야 합니다.")

    body = required_inputs.get("body")
    if body:
        required_fields = body.get("required_fields") or []
        if required_fields:
            questions.extend(
                f"요청 본문의 {field} 값을 확인해야 합니다." for field in required_fields
            )
        elif body.get("required"):
            questions.append("요청 본문에 필요한 필수 값을 확인해야 합니다.")

    return questions


def _response_interpretation(operation_kind: str) -> str:
    if operation_kind == "read":
        return "응답 데이터를 현재 상태 요약과 핵심 수치 중심으로 정리합니다."
    return "응답의 성공 여부와 생성 또는 변경된 핵심 결과를 사용자에게 요약합니다."


def _plan_template(summary: str, path: str, method: str, requires_confirmation: bool) -> list[str]:
    if not requires_confirmation:
        return []

    return [
        f"{summary or path} 실행에 필요한 입력값을 확인합니다.",
        f"{method} {path} 호출 전 영향 범위를 설명합니다.",
        f"{method} {path} 호출 결과를 검증하고 사용자에게 요약합니다.",
    ]


def build_metadata(operation: OpenAPIOperation) -> dict[str, Any]:
    operation_kind, usable_in, requires_confirmation, risk_level = infer_operation_kind(
        operation.method
    )

    return {
        "id": operation.id,
        "source_file": str(operation.source_file),
        "operation_id": operation.operation_id or None,
        "path": operation.path,
        "method": operation.method,
        "summary": operation.summary,
        "capability": operation.summary or operation.id,
        "usable_in": usable_in,
        "operation_kind": operation_kind,
        "when_to_use": [
            (
                f"사용자 요청이 '{operation.summary}'에 해당하는 작업일 때 사용합니다."
                if operation.summary
                else f"{operation.method} {operation.path} 호출이 필요한 요청일 때 사용합니다."
            )
        ],
        "when_not_to_use": [
            "다른 리소스를 조회하거나 변경하는 요청이면 사용하지 않습니다."
        ],
        "requires_confirmation": requires_confirmation,
        "risk_level": risk_level,
        "side_effects": [] if operation_kind == "read" else [operation.summary or operation.id],
        "required_headers": operation.required_headers,
        "required_inputs": operation.required_inputs,
        "preconditions": ["필수 입력값이 모두 준비되어 있어야 합니다."],
        "missing_info_questions": _collect_missing_info_questions(operation.required_inputs),
        "response_interpretation": _response_interpretation(operation_kind),
        "plan_template": _plan_template(
            operation.summary, operation.path, operation.method, requires_confirmation
        ),
        "examples": [operation.summary] if operation.summary else [],
    }


def merge_with_existing(generated: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    merged = dict(generated)
    for field in MANUAL_FIELDS:
        if field not in existing:
            continue
        value = existing[field]
        if value in (None, "", [], {}):
            continue
        merged[field] = value
    return merged


def write_metadata_file(output_path: Path, metadata: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def generate_registry(input_dir: Path, output_dir: Path) -> list[Path]:
    generated_paths: list[Path] = []
    operations_by_id: dict[str, OpenAPIOperation] = {}

    for openapi_path in sorted(input_dir.glob("*.yaml")):
        for operation in load_operations(openapi_path):
            existing = operations_by_id.get(operation.id)
            if existing:
                raise ValueError(
                    "Duplicate canonical id: "
                    f"{operation.id} "
                    f"({existing.source_file}:{existing.method} {existing.path}, "
                    f"{operation.source_file}:{operation.method} {operation.path})"
                )
            operations_by_id[operation.id] = operation

    for operation in sorted(operations_by_id.values(), key=lambda item: item.id):
        metadata = build_metadata(operation)
        output_path = output_dir / f"{operation.id}.ai.yaml"
        if output_path.exists():
            existing = yaml.safe_load(output_path.read_text(encoding="utf-8")) or {}
            metadata = merge_with_existing(metadata, existing)
        write_metadata_file(output_path, metadata)
        generated_paths.append(output_path)

    return generated_paths
