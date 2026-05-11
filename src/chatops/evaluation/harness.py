from __future__ import annotations

import json
from dataclasses import dataclass, field
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
    # Agent Loop 평가용
    executed_operation_ids: tuple[str, ...] = ()
    must_call_at_least_one_tool: bool | None = None


@dataclass(frozen=True)
class ScenarioCase:
    name: str
    message_text: str
    expectation: ScenarioExpectation
    session_id: int = 1
    user_id: str = "u1"
    user_role: str | None = "USER"
    org_id: str | None = None
    session_context: dict[str, object] | None = None
    # operation_id → canned response. ScenarioDispatcher가 매 시나리오마다 set_responses로 주입
    dispatch_responses: dict[str, dict[str, object]] | None = None
    # 장기 대화 히스토리 시뮬레이션: 실제 시나리오 실행 전 먼저 주입할 선행 턴
    # 각 항목: {"message_text": str, "dispatch_responses": dict (optional)}
    pre_turns: tuple[dict, ...] = ()
    # 승인 흐름 테스트: handle_request가 interrupted를 반환하면 resume_request를 자동 호출한다.
    # True → 승인, False → 거절, None → resume 없음
    resume_with: bool | None = None


@dataclass(frozen=True)
class ScenarioOutcome:
    name: str
    passed: bool
    failures: tuple[str, ...]
    dispatch_delta: int
    result: Any
    executed_operation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioReport:
    total_cases: int
    passed_cases: int
    outcomes: tuple[ScenarioOutcome, ...]
    metric_scores: dict[str, int]
    overall_score: int
    # Agent Loop 평가용 정량 지표
    agent_metrics: dict[str, float] = field(default_factory=dict)


_FALSE_COMPLETION_PATTERNS_FOR_METRIC = (
    "생성됐습니다", "생성되었습니다", "만들어졌습니다", "만들었습니다",
    "삭제됐습니다", "삭제되었습니다", "지워졌습니다",
    "변경됐습니다", "변경되었습니다", "수정됐습니다", "수정되었습니다",
    "추가됐습니다", "추가되었습니다",
    "완료됐습니다", "완료되었습니다",
    "이전됐습니다", "이전되었습니다",
)


def _looks_like_completion(text: str) -> bool:
    if not text:
        return False
    return any(pattern in text for pattern in _FALSE_COMPLETION_PATTERNS_FOR_METRIC)


class ScenarioRunner:
    def __init__(
        self,
        *,
        graph_service: Any,
        dispatch_count_getter: Callable[[], int] | None = None,
        metadata_getter: Callable[[Any], dict[str, Any]] | None = None,
        scenario_dispatcher: Any = None,
    ) -> None:
        self.graph_service = graph_service
        self.dispatch_count_getter = dispatch_count_getter or (lambda: 0)
        self.metadata_getter = metadata_getter or (lambda result: {})
        # ScenarioDispatcher가 주어지면 시나리오마다 응답을 갈아끼우고 executed_ids를 추적한다.
        self.scenario_dispatcher = scenario_dispatcher

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

        # Agent Loop 평가용 카운터
        false_completion_count = 0
        tool_selection_correct_count = 0
        tool_selection_check_count = 0
        iteration_total = 0
        iteration_check_count = 0
        any_tool_called_correct_count = 0
        any_tool_called_check_count = 0

        for scenario in scenarios:
            # 선행 턴(pre_turns): 실제 시나리오 전에 대화 히스토리를 쌓는다.
            # 동일 session_id + checkpointer 덕분에 LangGraph 상태에 히스토리가 누적된다.
            for pre_turn in scenario.pre_turns:
                if self.scenario_dispatcher is not None:
                    self.scenario_dispatcher.set_responses(
                        pre_turn.get("dispatch_responses") or {}
                    )
                    self.scenario_dispatcher.reset()
                pre_kwargs: dict[str, Any] = {
                    "session_id": scenario.session_id,
                    "user_id": scenario.user_id,
                    "user_role": scenario.user_role,
                    "org_id": scenario.org_id,
                    "message_text": pre_turn["message_text"],
                }
                preview_fn = getattr(self.graph_service, "preview_request", None)
                if callable(preview_fn):
                    pre_preview = preview_fn(message_text=pre_turn["message_text"])
                    if isinstance(pre_preview, dict):
                        if pre_preview.get("request_type"):
                            pre_kwargs["request_type"] = str(pre_preview["request_type"])
                        if pre_preview.get("intent"):
                            pre_kwargs["intent"] = str(pre_preview["intent"])
                self.graph_service.handle_request(**pre_kwargs)

            # ScenarioDispatcher가 있으면 매 시나리오마다 응답을 주입하고 추적을 리셋한다.
            if self.scenario_dispatcher is not None:
                self.scenario_dispatcher.set_responses(scenario.dispatch_responses or {})
                self.scenario_dispatcher.reset()

            before_dispatch = self.dispatch_count_getter()
            # 운영 흐름과 동일하게 preview_request로 먼저 분류한 뒤 그 결과를 handle_request에 주입.
            # request_type/intent가 없으면 _tool_choice_for_state가 항상 "auto"로 떨어져
            # toolChoice 사전 강제가 동작하지 않는다.
            handle_kwargs: dict[str, Any] = {
                "session_id": scenario.session_id,
                "user_id": scenario.user_id,
                "user_role": scenario.user_role,
                "org_id": scenario.org_id,
                "message_text": scenario.message_text,
                "session_context": scenario.session_context,
            }
            preview = getattr(self.graph_service, "preview_request", None)
            if callable(preview):
                preview_result = preview(
                    message_text=scenario.message_text,
                    session_context=scenario.session_context,
                )
                if isinstance(preview_result, dict):
                    if preview_result.get("request_type"):
                        handle_kwargs["request_type"] = str(preview_result["request_type"])
                    if preview_result.get("intent"):
                        handle_kwargs["intent"] = str(preview_result["intent"])
            result = self.graph_service.handle_request(**handle_kwargs)
            after_dispatch = self.dispatch_count_getter()
            dispatch_delta = after_dispatch - before_dispatch

            # 승인 흐름 테스트: interrupted 상태에서 resume_request 자동 호출
            if scenario.resume_with is not None and result.status == "interrupted":
                resume_fn = getattr(self.graph_service, "resume_request", None)
                if callable(resume_fn):
                    before_resume_dispatch = self.dispatch_count_getter()
                    result = resume_fn(
                        request_id=result.request_id,
                        session_id=scenario.session_id,
                        user_id=scenario.user_id,
                        message_text=scenario.message_text,
                        approval_granted=scenario.resume_with,
                        user_role=scenario.user_role,
                        org_id=scenario.org_id,
                    )
                    after_resume_dispatch = self.dispatch_count_getter()
                    dispatch_delta += after_resume_dispatch - before_resume_dispatch
                    # resume 이후 실행된 operation_id 포함
                    if self.scenario_dispatcher is not None:
                        executed_ids = list(self.scenario_dispatcher.executed_operation_ids)
            metadata = self.metadata_getter(result)

            # 시나리오에서 실제 호출된 operation_id 수집
            executed_ids: list[str] = []
            if self.scenario_dispatcher is not None:
                executed_ids = list(self.scenario_dispatcher.executed_operation_ids)
            iteration_total += len(executed_ids)
            iteration_check_count += 1

            # false_completion_rate: 완료 표현이 응답에 있으면서 실제 도구는 한 번도 호출 안 한 케이스
            response_text = result.final_response or ""
            if _looks_like_completion(response_text) and len(executed_ids) == 0:
                false_completion_count += 1
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

            # Agent Loop 전용: 실제 호출된 operation_id 시퀀스 검증
            if expectation.executed_operation_ids:
                expected_ids = list(expectation.executed_operation_ids)
                ok = list(executed_ids) == expected_ids
                tool_selection_check_count += 1
                if ok:
                    tool_selection_correct_count += 1
                else:
                    failures.append(
                        f"executed_operation_ids: expected {expected_ids}, got {executed_ids}"
                    )

            # Agent Loop 전용: 최소 한 번은 도구를 호출했는가
            if expectation.must_call_at_least_one_tool is not None:
                ok = (len(executed_ids) > 0) == expectation.must_call_at_least_one_tool
                any_tool_called_check_count += 1
                if ok:
                    any_tool_called_correct_count += 1
                else:
                    failures.append(
                        f"must_call_at_least_one_tool: expected {expectation.must_call_at_least_one_tool}, "
                        f"got executed_count={len(executed_ids)}"
                    )

            outcomes.append(
                ScenarioOutcome(
                    name=scenario.name,
                    passed=not failures,
                    failures=tuple(failures),
                    dispatch_delta=dispatch_delta,
                    result=result,
                    executed_operation_ids=tuple(executed_ids),
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

        # Agent Loop 정량 지표 집계
        agent_metrics: dict[str, float] = {}
        total_cases = len(scenarios)
        if total_cases > 0:
            agent_metrics["false_completion_rate"] = round(false_completion_count / total_cases, 4)
        if iteration_check_count > 0:
            agent_metrics["avg_iterations"] = round(iteration_total / iteration_check_count, 2)
        if tool_selection_check_count > 0:
            agent_metrics["tool_selection_accuracy"] = round(
                tool_selection_correct_count / tool_selection_check_count, 4
            )
        if any_tool_called_check_count > 0:
            agent_metrics["tool_invocation_rate"] = round(
                any_tool_called_correct_count / any_tool_called_check_count, 4
            )
        agent_metrics["false_completion_count"] = false_completion_count
        agent_metrics["total_cases"] = total_cases

        return ScenarioReport(
            total_cases=total_cases,
            passed_cases=passed_cases,
            outcomes=tuple(outcomes),
            metric_scores=metric_scores,
            overall_score=overall_score,
            agent_metrics=agent_metrics,
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
        user_role=raw.get("user_role", "USER"),
        org_id=raw.get("org_id"),
        session_context=raw.get("session_context"),
        dispatch_responses=raw.get("dispatch_responses"),
        pre_turns=tuple(raw.get("pre_turns", [])),
        resume_with=raw.get("resume_with"),
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
            executed_operation_ids=tuple(expectation.get("executed_operation_ids", [])),
            must_call_at_least_one_tool=expectation.get("must_call_at_least_one_tool"),
        ),
    )
