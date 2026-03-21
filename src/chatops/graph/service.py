from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from chatops.graph.nodes import WorkflowNodes
from chatops.graph.state import GraphState
from chatops.graph.workflow import GraphWorkflow


@dataclass(frozen=True)
class GraphResult:
    request_id: str
    session_id: str
    user_id: str
    status: str
    request_type: str
    requires_approval: bool
    intent: str
    final_response: str | None
    selected_operation_ids: list[str]


class GraphService:
    def __init__(self, llm_service, registry_service, adapter_service, resolver_service=None) -> None:
        self.workflow = GraphWorkflow(
            WorkflowNodes(
                llm_service=llm_service,
                registry_service=registry_service,
                adapter_service=adapter_service,
                resolver_service=resolver_service or _NullResolverService(),
            )
        ).compile()

    def handle_request(
        self,
        session_id: str,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        org_id: str | None = None,
    ) -> GraphResult:
        initial_state: GraphState = {
            "request_id": str(uuid4()),
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "org_id": org_id,
            "message_text": message_text,
            "approval_granted": False,
            "request_status": "created",
            "selected_operation_ids": [],
            "requires_approval": False,
        }
        return self._invoke(initial_state)

    def resume_request(
        self,
        request_id: str,
        session_id: str,
        user_id: str,
        message_text: str,
        user_role: str | None = None,
        org_id: str | None = None,
    ) -> GraphResult:
        initial_state: GraphState = {
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "org_id": org_id,
            "message_text": message_text,
            "approval_granted": True,
            "request_status": "approved",
            "selected_operation_ids": [],
            "requires_approval": False,
        }
        return self._invoke(initial_state)

    def _invoke(self, initial_state: GraphState) -> GraphResult:
        result = self.workflow.invoke(initial_state)
        return GraphResult(
            request_id=result["request_id"],
            session_id=result["session_id"],
            user_id=result["user_id"],
            status=result["request_status"],
            request_type=result["request_type"],
            requires_approval=bool(result.get("requires_approval", False)),
            intent=str(result.get("intent", "")),
            final_response=result.get("final_response"),
            selected_operation_ids=list(result.get("selected_operation_ids", [])),
        )


class _NullResolverService:
    def resolve(self, operation, message_text: str) -> dict[str, object]:
        return {}
