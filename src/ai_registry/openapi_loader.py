from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ai_registry.models import OpenAPIOperation


HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def singularize(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def normalize_operation_slug(
    source_stem: str,
    operation_id: str | None,
    path: str,
    method: str,
) -> str:
    base = (operation_id or "").strip().lower()
    method_lower = method.lower()

    if base:
        base = re.sub(rf"_endpoint_.*_{method_lower}$", "", base)
        base = re.sub(rf"_{method_lower}$", "", base)
        base = re.sub(r"_+", "_", base).strip("_")
    else:
        segments = [
            segment.strip("{}").replace("-", "_")
            for segment in path.split("/")
            if segment and not segment.startswith("{")
        ]
        path_params = [
            segment.strip("{}").replace("-", "_")
            for segment in path.split("/")
            if segment.startswith("{") and segment.endswith("}")
        ]
        if path_params:
            segments.extend(["by", *path_params])
        if method_lower == "get":
            base = "get_" + "_".join(segments or [source_stem])
        elif method_lower == "post":
            base = "create_" + "_".join(segments or [source_stem])
        elif method_lower == "delete":
            base = "delete_" + "_".join(segments or [source_stem])
        else:
            base = f"{method_lower}_" + "_".join(segments or [source_stem])

    tokens = [token for token in base.split("_") if token]
    if source_stem in tokens[1:]:
        source_index = tokens.index(source_stem)
        if source_index == 1:
            tokens = [tokens[0], *tokens[2:]]
        else:
            tokens = tokens[:source_index]
    source_tokens = {source_stem, singularize(source_stem)}
    verbs = {"create", "list", "get", "update", "delete", "check", "patch"}
    if len(tokens) >= 2 and tokens[0] in verbs and tokens[1] in source_tokens:
        tokens = [tokens[0], *tokens[2:]]

    semantic_slug = "_".join(tokens) or f"{method_lower}_{source_stem}"
    return f"{source_stem}.{semantic_slug}"


def _resolve_ref(document: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        return {}

    node: Any = document
    for part in ref[2:].split("/"):
        if not isinstance(node, dict):
            return {}
        node = node.get(part)
        if node is None:
            return {}

    if not isinstance(node, dict):
        return {}

    nested_ref = node.get("$ref")
    if nested_ref and nested_ref != ref:
        resolved = _resolve_ref(document, nested_ref)
        return {**resolved, **{key: value for key, value in node.items() if key != "$ref"}}

    return node


def _resolve_schema(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    schema_ref = schema.get("$ref")
    if not schema_ref:
        return schema

    resolved = _resolve_ref(document, schema_ref)
    return {**resolved, **{key: value for key, value in schema.items() if key != "$ref"}}


def _compact_schema(schema: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}

    for field in ("type", "format"):
        value = schema.get(field)
        if value:
            compact[field] = value

    enum_values = schema.get("enum")
    if enum_values:
        compact["enum"] = enum_values

    items = schema.get("items")
    if isinstance(items, dict):
        compact_items = _compact_schema(items)
        if compact_items:
            compact["items"] = compact_items

    return compact


def _extract_required_inputs(
    document: dict[str, Any], operation: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    required_inputs: dict[str, Any] = {
        "headers": [],
        "path": [],
        "query": [],
        "body": None,
    }

    for raw_parameter in operation.get("parameters", []):
        parameter = (
            _resolve_ref(document, raw_parameter["$ref"])
            if isinstance(raw_parameter, dict) and "$ref" in raw_parameter
            else raw_parameter
        )
        if not parameter.get("required", False):
            continue

        schema = _resolve_schema(document, parameter.get("schema", {}))
        entry = {
            "name": parameter["name"],
            "required": True,
        }
        entry.update(_compact_schema(schema))
        description = parameter.get("description")
        if description:
            entry["description"] = description

        location = parameter.get("in")
        if location == "header":
            required_inputs["headers"].append(entry)
        elif location == "path":
            required_inputs["path"].append(entry)
        elif location == "query":
            required_inputs["query"].append(entry)

    request_body = operation.get("requestBody")
    if request_body:
        content = request_body.get("content", {})
        if content:
            content_type, content_spec = next(iter(content.items()))
            raw_schema = content_spec.get("schema", {})
            schema = _resolve_schema(document, raw_schema)
            required_fields = list(schema.get("required", []))
            body_entry: dict[str, Any] = {
                "required": request_body.get("required", False) or bool(required_fields),
                "content_type": content_type,
            }
            if "$ref" in raw_schema:
                body_entry["schema_ref"] = raw_schema["$ref"]
            body_entry.update(_compact_schema(schema))
            if required_fields:
                body_entry["required_fields"] = required_fields
            required_inputs["body"] = body_entry

    required_headers = [entry["name"] for entry in required_inputs["headers"]]
    return required_headers, required_inputs


def load_operations(path: Path) -> list[OpenAPIOperation]:
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    operations: list[OpenAPIOperation] = []
    source_stem = path.stem

    for api_path, path_item in (document.get("paths") or {}).items():
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not operation:
                continue

            required_headers, required_inputs = _extract_required_inputs(document, operation)
            operation_id = operation.get("operationId") or ""
            canonical_id = normalize_operation_slug(
                source_stem=source_stem,
                operation_id=operation_id,
                path=api_path,
                method=method,
            )

            operations.append(
                OpenAPIOperation(
                    id=canonical_id,
                    source_file=path,
                    operation_id=operation_id,
                    path=api_path,
                    method=method.upper(),
                    summary=(operation.get("summary") or "").strip(),
                    required_headers=required_headers,
                    required_inputs=required_inputs,
                )
            )

    return sorted(operations, key=lambda operation: operation.id)
