from __future__ import annotations

import atexit
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from chatops.common.id_generator import IdGenerator
from chatops.graph.agent_loop import AgentGraph
from chatops.graph.session_message_service import SessionMessageService
from chatops.services.decision_trace import log_decision_trace
from chatops.services.response_streaming import response_stream_handler_context
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
        llm_service: Any,
        registry_service: Any,
        adapter_service: Any = None,
        downstream_dispatcher: Any = None,
        resolver_service: Any = None,
        checkpointer: Any = None,
        database_url: str | None = None,
        approval_ttl_seconds: int = 900,
        # 하위 호환: use_agent_loop 파라미터를 받되 무시한다.
        use_agent_loop: bool = True,
    ) -> None:
        self._exit_stack = ExitStack()
        self._closed = False
        self.approval_ttl_seconds = approval_ttl_seconds
        self.llm_service = llm_service
        self.checkpointer = checkpointer or self._build_checkpointer(database_url)

        dispatcher = downstream_dispatcher or adapter_service
        if dispatcher is None:
            raise ValueError("downstream dispatcher is required")

        agent_graph = AgentGraph(
            llm_service=llm_service,
            registry_service=registry_service,
            downstream_dispatcher=dispatcher,
            resolver_service=resolver_service or _NullResolverService(),
            approval_ttl_seconds=approval_ttl_seconds,
        )
        self.workflow = agent_graph.compile(checkpointer=self.checkpointer)
        atexit.register(self.close)

    def preview_request(
        self,
        message_text: str,
        session_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        effective_message_text = SessionMessageService().effective_message_text(
            {
                "message_text": message_text,
                "session_context": session_context,
            }
        )
        classification = self.llm_service.classify(effective_message_text)
        log_decision_trace(
            stage="preview_request",
            decision=str(classification["request_type"]),
            reason="preview classification completed",
            data={
                "message_text": message_text,
                "effective_message_text": effective_message_text,
                "intent": str(classification.get("intent", "")),
            },
        )
        return {
            "request_type": str(classification["request_type"]),
            "intent": str(classification.get("intent", "")),
            "effective_message_text": effective_message_text,
        }

    def handle_request(
        self,
        session_id: int,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        org_id: str | None = None,
        session_context: dict[str, object] | None = None,
        request_id: int | None = None,
        request_type: str | None = None,
        intent: str | None = None,
        response_stream_handler: Callable[[str], None] | None = None,
    ) -> GraphResult:
        from chatops.graph.agent_state import AgentState

        request_id = request_id or IdGenerator.generate_sonyflake_id()
        now = datetime.now(timezone.utc).isoformat()

        initial_state: AgentState = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "org_id": org_id,
            # messages는 _append_messages reducer로 누적된다 (Bedrock dict 형태 유지).
            # 동일 session_id의 이전 대화 내용이 있으면 자동으로 이어진다.
            "messages": [
                {"role": "user", "content": [{"text": message_text}]},
            ],
            "session_context": session_context,
            "request_type": request_type,
            "intent": intent,
            "approval_granted": False,
            "request_status": "processing",
            "executed_operations": [],
            "pending_tool_call": None,
            "correction_attempts": 0,
            "created_at": now,
        }
        # session_id를 thread_id로 사용 → 같은 세션의 메시지 히스토리가 누적된다.
        config = self._session_config(session_id)
        with response_stream_handler_context(response_stream_handler):
            result = self.workflow.invoke(initial_state, config=config)

        return self._build_agent_result(
            result=result,
            config=config,
            initial_state=initial_state,
        )

    def resume_request(
        self,
        request_id: int,
        session_id: int,
        user_id: str,
        message_text: str,
        approval_granted: bool | str = True,
        user_role: str | None = None,
        org_id: str | None = None,
        response_stream_handler: Callable[[str], None] | None = None,
    ) -> GraphResult:
        fallback_state = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "org_id": org_id,
        }
        # handle_request와 동일한 session_id 기반 thread_id 사용
        config = self._session_config(session_id)
        with response_stream_handler_context(response_stream_handler):
            result = self.workflow.invoke(Command(resume=approval_granted), config=config)

        return self._build_agent_result(
            result=result,
            config=config,
            initial_state=fallback_state,
        )

    def _build_agent_result(
        self,
        result: dict[str, object],
        config: dict[str, object],
        initial_state: dict[str, object],
    ) -> GraphResult:
        snapshot = self.workflow.get_state(config)
        state: dict[str, Any] = dict(initial_state)
        state.update(snapshot.values)
        state.update({k: v for k, v in result.items() if k != "__interrupt__"})

        # interrupt()가 발생한 경우 승인 대기 상태로 표시
        is_interrupted = "__interrupt__" in result
        if is_interrupted:
            status = "interrupted"
            requires_approval = True
        else:
            status = str(state.get("request_status", "created"))
            requires_approval = False

        return GraphResult(
            request_id=int(state["request_id"]),
            session_id=int(state["session_id"]),
            user_id=str(state["user_id"]),
            status=status,
            request_type="agent",
            requires_approval=requires_approval,
            intent=str(state.get("intent") or ""),
            final_response=state.get("final_response"),
            selected_operation_ids=[
                op["operation_id"]
                for op in (state.get("executed_operations") or [])
                if isinstance(op, dict) and op.get("operation_id")
            ],
            execution_audit=state.get("execution_audit"),
            task_snapshot=state.get("task_snapshot"),
        )

    def reset_session_thread(self, session_id: int) -> None:
        """supersede 시 이전 interrupted 상태의 스테일 필드를 checkpoint에서 초기화한다.

        LangGraph가 새 invoke 전에 pending_tool_call 등을 이어받지 않도록 보장한다.
        checkpoint가 없으면 no-op.
        """
        config = self._session_config(session_id)
        try:
            snapshot = self.workflow.get_state(config)
        except Exception:
            return
        if snapshot is None or not snapshot.values:
            return
        self.workflow.update_state(
            config,
            {
                "pending_tool_call": None,
                "request_status": "processing",
                "executed_operations": [],
                "correction_attempts": 0,
            },
        )

    def _session_config(self, session_id: int) -> dict[str, object]:
        """세션 기반 thread 설정. 동일 session_id는 대화 히스토리를 공유한다."""
        return {"configurable": {"thread_id": f"sess_{session_id}"}}

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
