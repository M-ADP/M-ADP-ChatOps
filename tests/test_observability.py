from __future__ import annotations

from dataclasses import dataclass
import json
import logging

from chatops.db.repositories import RequestRepository, SessionRepository
from chatops.graph.service import GraphService
from chatops.services.events import EventService
from chatops.services.registry import RegistryEntry, ScoredCandidate
from chatops.services.resolver import ParameterResolverService


@dataclass
class _FakeLLMService:
    def classify(self, message_text: str) -> dict[str, object]:
        del message_text
        return {
            "request_type": "query",
            "intent": "query_status",
            "classification_reason": "조회 요청",
            "classification_confidence": 0.95,
        }

    def answer_inquiry(
        self,
        message_text: str,
        supported_operations: list[dict[str, object]] | None = None,
    ) -> str:
        del message_text, supported_operations
        return "문의 응답"

    def interpret_query_result(self, message_text: str, raw_result: dict[str, object]) -> str:
        del message_text
        return str(raw_result["summary"])


@dataclass
class _PlanningLLMService(_FakeLLMService):
    def classify(self, message_text: str) -> dict[str, object]:
        del message_text
        return {
            "request_type": "command",
            "intent": "provision_application",
            "classification_reason": "생성 명령",
            "classification_confidence": 0.98,
        }

    def build_plan_object(
        self,
        message_text: str,
        request_type: str,
        candidate_operation_ids: list[str],
    ) -> dict[str, object]:
        return {
            "goal": message_text,
            "specialist": "application",
            "entities": {"project_name": "demo"},
            "constraints": {"approval_required": True, "request_type": request_type},
            "candidate_steps": [
                {
                    "step_id": "create-app",
                    "title": "애플리케이션 생성",
                    "status": "planned",
                    "operation_id": candidate_operation_ids[0],
                },
                {
                    "step_id": "check-status",
                    "title": "생성 상태 확인",
                    "status": "planned",
                    "operation_id": "application.get_apps_status",
                },
            ],
            "risk_level": "medium",
            "required_clarifications": ["port"],
        }


def _query_entry(entry_id: str) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file="test",
        operation_id=entry_id,
        path="/apps/logs",
        method="GET",
        summary=entry_id,
        capability=entry_id,
        usable_in=("query",),
        operation_kind="read",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=False,
        risk_level="low",
        side_effects=(),
        required_headers=("X-User-Id",),
        required_inputs={"headers": [], "path": [], "query": [], "body": None},
        important_inputs={"path": [], "query": [], "body": []},
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="",
        plan_template=(),
        examples=(),
    )


def _command_entry(entry_id: str) -> RegistryEntry:
    return RegistryEntry(
        id=entry_id,
        source_file="test",
        operation_id=entry_id,
        path="/apps",
        method="POST",
        summary=entry_id,
        capability=entry_id,
        usable_in=("command",),
        operation_kind="write",
        when_to_use=(),
        when_not_to_use=(),
        requires_confirmation=True,
        risk_level="medium",
        side_effects=(),
        required_headers=("X-User-Id",),
        required_inputs={"headers": [], "path": [], "query": [], "body": {"required": True, "required_fields": []}},
        important_inputs={"body": []},
        preconditions=(),
        missing_info_questions=(),
        response_interpretation="",
        plan_template=(),
        examples=(),
    )


@dataclass
class _FallbackRegistryService:
    def find_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[RegistryEntry]:
        del user_text, limit
        assert usable_in == "query"
        return [_query_entry("application.get_apps_logs")]

    def find_scored_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[ScoredCandidate]:
        return [ScoredCandidate(entry=self.find_candidates(user_text, usable_in, limit)[0], score=100)]

    def detect_ambiguity(self, scored_candidates: list[ScoredCandidate]) -> tuple[bool, list[ScoredCandidate]]:
        del scored_candidates
        return False, []

    def get_entry(self, entry_id: str) -> RegistryEntry | None:
        return _query_entry(entry_id)


@dataclass
class _CommandRegistryService:
    def find_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[RegistryEntry]:
        del user_text, limit
        assert usable_in == "command"
        return [_command_entry("application.create_apps")]

    def find_scored_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[ScoredCandidate]:
        return [ScoredCandidate(entry=self.find_candidates(user_text, usable_in, limit)[0], score=100)]

    def detect_ambiguity(self, scored_candidates: list[ScoredCandidate]) -> tuple[bool, list[ScoredCandidate]]:
        del scored_candidates
        return False, []

    def get_entry(self, entry_id: str) -> RegistryEntry | None:
        return _command_entry(entry_id)


@dataclass
class _AmbiguousRegistryService:
    def find_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[RegistryEntry]:
        del user_text, usable_in, limit
        return [_query_entry("project.get"), _query_entry("application.get_apps_status")]

    def find_scored_candidates(self, user_text: str, usable_in: str, limit: int = 5) -> list[ScoredCandidate]:
        entries = self.find_candidates(user_text, usable_in, limit)
        return [ScoredCandidate(entry=entries[0], score=100), ScoredCandidate(entry=entries[1], score=99)]

    def detect_ambiguity(self, scored_candidates: list[ScoredCandidate]) -> tuple[bool, list[ScoredCandidate]]:
        return True, scored_candidates[:2]

    def get_entry(self, entry_id: str) -> RegistryEntry | None:
        return _query_entry(entry_id)


@dataclass
class _FallbackDispatcher:
    async def execute_query(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del operation, user_id, user_role, org_id, resolved_inputs
        return {
            "success": False,
            "summary": "대상 리소스를 찾지 못했습니다.",
            "status_code": 404,
            "fallback_used": True,
        }

    async def execute_command(
        self,
        operation: RegistryEntry,
        user_id: str,
        user_role: str | None = None,
        org_id: str | None = None,
        resolved_inputs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del operation, user_id, user_role, org_id, resolved_inputs
        return {"success": True, "summary": "ok"}


def _parse_log_json(record: logging.LogRecord) -> dict[str, object]:
    message = record.getMessage()
    return json.loads(message.split(" ", 1)[1])


def test_downstream_execution_logs_include_fallback_and_request_context(caplog) -> None:
    caplog.set_level(logging.INFO, logger="chatops.graph.nodes")
    graph_service = GraphService(
        llm_service=_FakeLLMService(),
        registry_service=_FallbackRegistryService(),
        adapter_service=_FallbackDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1001,
        user_id="user-1",
        message_text="앱 로그 보여줘",
    )

    assert result.status == "input_required"
    assert result.verifier_decision is not None
    assert result.verifier_decision["decision"] == "clarify"
    execution_logs = [record for record in caplog.records if record.getMessage().startswith("downstream_execution ")]
    assert execution_logs
    payload = _parse_log_json(execution_logs[-1])
    assert payload["request_id"] == result.request_id
    assert payload["session_id"] == 1001
    assert payload["user_id"] == "user-1"
    assert payload["operation"] == "application.get_apps_logs"
    assert payload["downstream"] == "application"
    assert payload["status_code"] == 404
    assert payload["fallback_used"] is True
    assert payload["clarification_type"] is None
    assert isinstance(payload["latency_ms"], float)


def test_clarification_logs_include_type_and_request_context(caplog) -> None:
    caplog.set_level(logging.INFO, logger="chatops.graph.nodes")
    graph_service = GraphService(
        llm_service=_FakeLLMService(),
        registry_service=_AmbiguousRegistryService(),
        adapter_service=_FallbackDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1002,
        user_id="user-2",
        message_text="demo 상태 보여줘",
    )

    assert result.status == "ambiguous"
    clarification_logs = [record for record in caplog.records if record.getMessage().startswith("clarification_event ")]
    assert clarification_logs
    payload = _parse_log_json(clarification_logs[-1])
    assert payload["request_id"] == result.request_id
    assert payload["session_id"] == 1002
    assert payload["user_id"] == "user-2"
    assert payload["clarification_type"] == "ambiguity"
    assert payload["fallback_used"] is False
    assert payload["operation"] is None
    assert payload["status_code"] is None


def test_event_service_append_audit_event_includes_normalized_context(db_session) -> None:
    session = SessionRepository(db_session).create(user_id="user-1", title=None)
    request = RequestRepository(db_session).create(
        session_id=session.id,
        user_id="user-1",
        message_text="앱 로그 보여줘",
    )
    service = EventService(db_session)

    record = service.append_audit_event(
        request_id=request.id,
        session_id=session.id,
        event_type="execution.failed",
        payload={"type": "execution.failed"},
        audit_context={
            "user_id": "user-1",
            "operation": "application.get_apps_logs",
            "latency_ms": 12.34,
            "downstream": "application",
            "status_code": 404,
            "fallback_used": True,
            "clarification_type": None,
        },
    )

    payload = json.loads(record.payload)
    assert payload["request_id"] == request.id
    assert payload["session_id"] == session.id
    assert payload["user_id"] == "user-1"
    assert payload["operation"] == "application.get_apps_logs"
    assert payload["latency_ms"] == 12.34
    assert payload["downstream"] == "application"
    assert payload["status_code"] == 404
    assert payload["fallback_used"] is True
    assert "clarification_type" in payload


def test_preview_request_logs_classification_trace(caplog) -> None:
    caplog.set_level(logging.INFO, logger="chatops.decision_trace")
    graph_service = GraphService(
        llm_service=_FakeLLMService(),
        registry_service=_FallbackRegistryService(),
        adapter_service=_FallbackDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    preview = graph_service.preview_request("앱 로그 보여줘")

    assert preview["request_type"] == "query"
    trace_logs = [record for record in caplog.records if record.name == "chatops.decision_trace"]
    payloads = [_parse_log_json(record) for record in trace_logs]
    preview_payload = next(payload for payload in payloads if payload["stage"] == "preview_request")
    assert preview_payload["decision"] == "query"
    assert preview_payload["data"]["intent"] == "query_status"


def test_handle_request_logs_plan_runtime_trace(caplog) -> None:
    caplog.set_level(logging.INFO, logger="chatops.decision_trace")
    graph_service = GraphService(
        llm_service=_PlanningLLMService(),
        registry_service=_CommandRegistryService(),
        adapter_service=_FallbackDispatcher(),
        resolver_service=ParameterResolverService(),
    )

    result = graph_service.handle_request(
        session_id=1003,
        user_id="user-3",
        message_text="demo 프로젝트에 애플리케이션 생성해",
    )

    assert result.plan_object is not None
    trace_logs = [record for record in caplog.records if record.name == "chatops.decision_trace"]
    payloads = [_parse_log_json(record) for record in trace_logs]
    plan_payload = next(payload for payload in payloads if payload["stage"] == "plan_runtime")
    assert plan_payload["decision"] == "command"
    assert plan_payload["request_id"] == result.request_id
    assert plan_payload["session_id"] == 1003
    assert plan_payload["user_id"] == "user-3"
    assert plan_payload["data"]["goal"] == "demo 프로젝트에 앱 생성해"
    assert plan_payload["data"]["specialist"] == "application"
    assert plan_payload["data"]["risk_level"] == "medium"
    assert plan_payload["data"]["required_clarifications"] == ["port"]
    assert plan_payload["data"]["candidate_steps"] == [
        {
            "step_id": "create-app",
            "title": "애플리케이션 생성",
            "status": "planned",
            "operation_id": "application.create_apps",
        },
        {
            "step_id": "check-status",
            "title": "생성 상태 확인",
            "status": "planned",
            "operation_id": "application.get_apps_status",
        },
    ]
