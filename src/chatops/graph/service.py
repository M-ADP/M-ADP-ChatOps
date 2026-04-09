from __future__ import annotations

import atexit
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone

from chatops.common.id_generator import IdGenerator
from chatops.domain.enums import RequestStatus
from chatops.graph.nodes import WorkflowNodes
from chatops.graph.state import GraphState
from chatops.graph.workflow import GraphWorkflow
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command


@dataclass(frozen=True)
class GraphResult:
    request_id: int
    session_id: int
    user_id: str
    status: str
    request_type: str
    requires_approval: bool
    intent: str
    final_response: str | None
    selected_operation_ids: list[str]
    missing_inputs: list[str] | None = None
    effective_message_text: str | None = None
    resolved_references: dict[str, object] | None = None
    resolved_ids: dict[str, object] | None = None
    is_ambiguous: bool = False
    ambiguity_candidates: list[dict[str, object]] | None = None
    risk_level: str | None = None
    error_code: str | None = None
    expires_at: str | None = None
    clarification_type: str | None = None
    fallback_used: bool = False
    execution_audit: dict[str, object] | None = None
    task_snapshot: dict[str, object] | None = None
    plan_object: dict[str, object] | None = None
    verifier_decision: dict[str, object] | None = None
    specialist_result: dict[str, object] | None = None
    session_summary: dict[str, object] | None = None


class GraphService:
    def __init__(
        self,
        llm_service,
        registry_service,
        adapter_service=None,
        downstream_dispatcher=None,
        resolver_service=None,
        checkpointer=None,
        database_url: str | None = None,
        approval_ttl_seconds: int = 900,
    ) -> None:
        self._exit_stack = ExitStack()
        self._closed = False
        self.approval_ttl_seconds = approval_ttl_seconds
        self.checkpointer = checkpointer or self._build_checkpointer(database_url)
        dispatcher = downstream_dispatcher or adapter_service
        if dispatcher is None:
            raise ValueError("downstream dispatcher is required")
        self.workflow = GraphWorkflow(
            WorkflowNodes(
                llm_service=llm_service,
                registry_service=registry_service,
                downstream_dispatcher=dispatcher,
                resolver_service=resolver_service or _NullResolverService(),
                approval_ttl_seconds=approval_ttl_seconds,
            )
        ).compile(checkpointer=self.checkpointer)
        atexit.register(self.close)

    def handle_request(
        self,
        session_id: int,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        org_id: str | None = None,
        session_context: dict[str, object] | None = None,
    ) -> GraphResult:
        request_id = IdGenerator.generate_sonyflake_id()
        initial_state: GraphState = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "org_id": org_id,
            "message_text": message_text,
            "session_context": session_context,
            "approval_granted": False,
            "request_status": "created",
            "selected_operation_ids": [],
            "requires_approval": False,
            "is_ambiguous": False,
            "ambiguity_candidates": [],
        }
        return self._invoke(initial_state, config=self._thread_config(request_id))

    def resume_request(
        self,
        request_id: int,
        session_id: int,
        user_id: str,
        message_text: str,
        approval_granted: bool | str = True,
        user_role: str | None = None,
        org_id: str | None = None,
    ) -> GraphResult:
        fallback_state: GraphState = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "org_id": org_id,
            "message_text": message_text,
            "approval_granted": approval_granted,
        }
        config = self._thread_config(request_id)
        result = self.workflow.invoke(Command(resume=approval_granted), config=config)
        return self._build_result(result=result, config=config, fallback_state=fallback_state)

    def _invoke(self, initial_state: GraphState, config: dict[str, object]) -> GraphResult:
        result = self.workflow.invoke(initial_state, config=config)
        return self._build_result(result=result, config=config, fallback_state=initial_state)

    def _build_result(
        self,
        result: dict[str, object],
        config: dict[str, object],
        fallback_state: GraphState,
    ) -> GraphResult:
        snapshot = self.workflow.get_state(config)
        state = dict(fallback_state)
        state.update(snapshot.values)
        state.update({key: value for key, value in result.items() if key != "__interrupt__"})
        return GraphResult(
            request_id=int(state["request_id"]),
            session_id=int(state["session_id"]),
            user_id=str(state["user_id"]),
            status=str(state.get("request_status", "created")),
            request_type=str(state.get("request_type", "")),
            requires_approval=bool(state.get("requires_approval", False)),
            intent=str(state.get("intent", "")),
            final_response=state.get("final_response"),
            selected_operation_ids=list(state.get("selected_operation_ids", [])),
            missing_inputs=list(state.get("missing_inputs", [])) or None,
            effective_message_text=state.get("effective_message_text"),
            resolved_references=self._extract_references(state),
            resolved_ids=self._extract_resolved_ids(state),
            is_ambiguous=bool(state.get("is_ambiguous", False)),
            ambiguity_candidates=state.get("ambiguity_candidates"),
            risk_level=state.get("risk_level"),
            error_code=state.get("error_code"),
            expires_at=state.get("expires_at"),
            clarification_type=state.get("clarification_type"),
            fallback_used=bool(state.get("fallback_used", False)),
            execution_audit=state.get("execution_audit"),
            task_snapshot=state.get("task_snapshot"),
            plan_object=state.get("plan_object"),
            verifier_decision=state.get("verifier_decision"),
            specialist_result=state.get("specialist_result"),
            session_summary=state.get("session_summary"),
        )

    def _extract_references(self, state: dict[str, object]) -> dict[str, object] | None:
        resolved_inputs = state.get("resolved_inputs")
        if isinstance(resolved_inputs, dict):
            refs = resolved_inputs.get("references")
            if isinstance(refs, dict) and refs:
                return dict(refs)
        return None

    def _extract_resolved_ids(self, state: dict[str, object]) -> dict[str, object] | None:
        resolved_inputs = state.get("resolved_inputs")
        if isinstance(resolved_inputs, dict):
            resolved_ids = resolved_inputs.get("resolved_ids")
            if isinstance(resolved_ids, dict) and resolved_ids:
                return dict(resolved_ids)
        return None

    def _thread_config(self, request_id: int) -> dict[str, object]:
        return {"configurable": {"thread_id": str(request_id)}}

    def _build_checkpointer(self, database_url: str | None):
        if database_url and database_url.startswith("postgresql"):
            conn_string = database_url.replace("+psycopg", "", 1)
            saver = self._exit_stack.enter_context(PostgresSaver.from_conn_string(conn_string))
            saver.setup()
            return saver
        return InMemorySaver()

    def close(self) -> None:
        if self._closed:
            return
        self._exit_stack.close()
        self._closed = True


class _NullResolverService:
    def resolve(self, operation, message_text: str, session_context: dict[str, object] | None = None) -> dict[str, object]:
        del session_context
        return {}
