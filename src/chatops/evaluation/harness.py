from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Callable, Any


@dataclass(frozen=True)
class ScenarioExpectation:
    status: str | None = None
    request_type: str | None = None
    error_code: str | None = None
    requires_approval: bool | None = None
    is_ambiguous: bool | None = None
    missing_inputs: tuple[str, ...] = ()
    selected_operation_ids: tuple[str, ...] = ()
    resolved_references: dict[str, object] | None = None
    response_contains: tuple[str, ...] = ()
    clarification_contains: tuple[str, ...] = ()
    fallback_used: bool | None = None
    permission_denied: bool | None = None
    dispatched: bool | None = None


@dataclass(frozen=True)
class ScenarioCase:
    name: str
    message_text: str
    expectation: ScenarioExpectation
    session_id: int = 1
    user_id: str = "u1"
    session_context: dict[str, object] | None = None


@dataclass(frozen=True)
class ScenarioOutcome:
    name: str
    passed: bool
    failures: tuple[str, ...]
    dispatch_delta: int
    result: Any


@dataclass(frozen=True)
class ScenarioReport:
    total_cases: int
    passed_cases: int
    outcomes: tuple[ScenarioOutcome, ...]
    metric_scores: dict[str, int]
    overall_score: int


class ScenarioRunner:
    def __init__(
        self,
        *,
        graph_service: Any,
        dispatch_count_getter: Callable[[], int] | None = None,
        metadata_getter: Callable[[Any], dict[str, Any]] | None = None,
    ) -> None:
        self.graph_service = graph_service
        self.dispatch_count_getter = dispatch_count_getter or (lambda: 0)
        self.metadata_getter = metadata_getter or (lambda result: {})

    def run(self, scenarios: list[ScenarioCase]) -> ScenarioReport:
        outcomes: list[ScenarioOutcome] = []
        metric_checks: dict[str, list[bool]] = {
            "status_accuracy": [],
            "request_type_accuracy": [],
            "error_code_accuracy": [],
            "slot_accuracy": [],
            "response_quality": [],
            "clarification_behavior": [],
            "safety_behavior": [],
        }
        metadata_metric_values: dict[str, list[int]] = {
            "workflow_correctness": [],
            "maintainability": [],
            "extensibility": [],
        }

        for scenario in scenarios:
            before_dispatch = self.dispatch_count_getter()
            result = self.graph_service.handle_request(
                session_id=scenario.session_id,
                user_id=scenario.user_id,
                message_text=scenario.message_text,
                session_context=scenario.session_context,
            )
            after_dispatch = self.dispatch_count_getter()
            dispatch_delta = after_dispatch - before_dispatch
            metadata = self.metadata_getter(result)
            for metric_name in metadata_metric_values:
                value = metadata.get(metric_name)
                if isinstance(value, (int, float)):
                    metadata_metric_values[metric_name].append(int(round(value)))

            failures: list[str] = []
            expectation = scenario.expectation

            if expectation.status is not None:
                ok = result.status == expectation.status
                metric_checks["status_accuracy"].append(ok)
                if not ok:
                    failures.append(f"status: expected {expectation.status}, got {result.status}")

            if expectation.request_type is not None:
                ok = result.request_type == expectation.request_type
                metric_checks["request_type_accuracy"].append(ok)
                if not ok:
                    failures.append(f"request_type: expected {expectation.request_type}, got {result.request_type}")

            if expectation.error_code is not None:
                ok = result.error_code == expectation.error_code
                metric_checks["error_code_accuracy"].append(ok)
                if not ok:
                    failures.append(f"error_code: expected {expectation.error_code}, got {result.error_code}")

            if expectation.requires_approval is not None:
                ok = bool(getattr(result, "requires_approval", False)) == expectation.requires_approval
                metric_checks["safety_behavior"].append(ok)
                if not ok:
                    failures.append(
                        f"requires_approval: expected {expectation.requires_approval}, got {getattr(result, 'requires_approval', False)}"
                    )

            if expectation.is_ambiguous is not None:
                ok = bool(getattr(result, "is_ambiguous", False)) == expectation.is_ambiguous
                metric_checks["clarification_behavior"].append(ok)
                if not ok:
                    failures.append(
                        f"is_ambiguous: expected {expectation.is_ambiguous}, got {getattr(result, 'is_ambiguous', False)}"
                    )

            if expectation.missing_inputs:
                actual_missing = tuple(result.missing_inputs or [])
                ok = actual_missing == expectation.missing_inputs
                metric_checks["slot_accuracy"].append(ok)
                if not ok:
                    failures.append(f"missing_inputs: expected {expectation.missing_inputs}, got {actual_missing}")

            if expectation.selected_operation_ids:
                actual_selected = tuple(result.selected_operation_ids)
                ok = actual_selected == expectation.selected_operation_ids
                metric_checks["slot_accuracy"].append(ok)
                if not ok:
                    failures.append(
                        f"selected_operation_ids: expected {expectation.selected_operation_ids}, got {actual_selected}"
                    )

            if expectation.resolved_references is not None:
                ok = result.resolved_references == expectation.resolved_references
                metric_checks["slot_accuracy"].append(ok)
                if not ok:
                    failures.append(
                        f"resolved_references: expected {expectation.resolved_references}, got {result.resolved_references}"
                    )

            if expectation.response_contains:
                response = result.final_response or ""
                ok = all(fragment in response for fragment in expectation.response_contains)
                metric_checks["response_quality"].append(ok)
                if not ok:
                    failures.append(f"response missing expected fragments: {expectation.response_contains}")

            if expectation.clarification_contains:
                response = result.final_response or ""
                ok = all(fragment in response for fragment in expectation.clarification_contains)
                metric_checks["clarification_behavior"].append(ok)
                if not ok:
                    failures.append(f"clarification missing expected fragments: {expectation.clarification_contains}")

            if expectation.fallback_used is not None:
                actual_fallback = bool(metadata.get("fallback_used", False))
                ok = actual_fallback == expectation.fallback_used
                metric_checks["safety_behavior"].append(ok)
                if not ok:
                    failures.append(f"fallback_used: expected {expectation.fallback_used}, got {actual_fallback}")

            if expectation.permission_denied is not None:
                actual_permission_denied = bool(metadata.get("permission_denied", False))
                ok = actual_permission_denied == expectation.permission_denied
                metric_checks["safety_behavior"].append(ok)
                if not ok:
                    failures.append(
                        f"permission_denied: expected {expectation.permission_denied}, got {actual_permission_denied}"
                    )

            if expectation.dispatched is not None:
                actual_dispatched = dispatch_delta > 0
                ok = actual_dispatched == expectation.dispatched
                metric_checks["safety_behavior"].append(ok)
                if not ok:
                    failures.append(
                        f"dispatched: expected {expectation.dispatched}, got {actual_dispatched}"
                    )

            outcomes.append(
                ScenarioOutcome(
                    name=scenario.name,
                    passed=not failures,
                    failures=tuple(failures),
                    dispatch_delta=dispatch_delta,
                    result=result,
                )
            )

        metric_scores = {
            metric: int(round(mean([100 if passed else 0 for passed in checks])))
            for metric, checks in metric_checks.items()
            if checks
        }
        metric_scores.update(
            {
                metric: int(round(mean(values)))
                for metric, values in metadata_metric_values.items()
                if values
            }
        )
        overall_score = int(round(mean(list(metric_scores.values())))) if metric_scores else 100
        passed_cases = sum(1 for outcome in outcomes if outcome.passed)
        return ScenarioReport(
            total_cases=len(scenarios),
            passed_cases=passed_cases,
            outcomes=tuple(outcomes),
            metric_scores=metric_scores,
            overall_score=overall_score,
        )


DEFAULT_QUALITY_SCENARIOS_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "quality_scenarios.json"
)


def load_quality_scenarios(path: Path | str | None = None) -> list[ScenarioCase]:
    scenario_path = Path(path) if path is not None else DEFAULT_QUALITY_SCENARIOS_PATH
    raw = json.loads(scenario_path.read_text(encoding="utf-8"))
    return [_build_scenario_case(item) for item in raw]


def _build_scenario_case(raw: dict[str, Any]) -> ScenarioCase:
        expectation = raw.get("expectation", {})
        return ScenarioCase(
        name=str(raw["name"]),
        message_text=str(raw["message_text"]),
        session_id=int(raw.get("session_id", 1)),
        user_id=str(raw.get("user_id", "u1")),
        session_context=raw.get("session_context"),
        expectation=ScenarioExpectation(
            status=expectation.get("status"),
            request_type=expectation.get("request_type"),
            error_code=expectation.get("error_code"),
            requires_approval=expectation.get("requires_approval"),
            is_ambiguous=expectation.get("is_ambiguous"),
            missing_inputs=tuple(expectation.get("missing_inputs", [])),
            selected_operation_ids=tuple(expectation.get("selected_operation_ids", [])),
            resolved_references=expectation.get("resolved_references"),
            response_contains=tuple(expectation.get("response_contains", [])),
            clarification_contains=tuple(expectation.get("clarification_contains", [])),
            fallback_used=expectation.get("fallback_used"),
            permission_denied=expectation.get("permission_denied"),
            dispatched=expectation.get("dispatched"),
        ),
    )
