from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from chatops.graph.nodes import WorkflowNodes
from chatops.graph.state import GraphState


def _route_after_advance_step(state: GraphState) -> str:
    """advance_step 이후 라우팅: 다음 단계가 있으면 재실행, 없으면 종료 노드로."""
    current_index = int(state.get("current_step_index", 0))
    total_steps = int(state.get("total_steps", 0))
    request_type = state.get("request_type", "command")

    if current_index < total_steps:
        return f"next_{request_type}"   # "next_command" | "next_query"
    return f"done_{request_type}"       # "done_command"  | "done_query"


class GraphWorkflow:
    def __init__(self, nodes: WorkflowNodes) -> None:
        self.nodes = nodes

    def compile(self, checkpointer=None):
        graph = StateGraph(GraphState)
        graph.add_node("ingest_request", self.nodes.ingest_request)
        graph.add_node("classify_request", self.nodes.classify_request)
        graph.add_node("plan_runtime", self.nodes.plan_runtime)
        graph.add_node("route_request", self.nodes.route_request)
        graph.add_node("answer_inquiry", self.nodes.answer_inquiry)
        graph.add_node("prepare_query", self.nodes.prepare_query)
        graph.add_node("execute_query", self.nodes.execute_query)
        graph.add_node("verify_query", self.nodes.verify_query)
        graph.add_node("interpret_result", self.nodes.interpret_result)
        graph.add_node("finalize_query_verifier_outcome", self.nodes.finalize_query_verifier_outcome)
        graph.add_node("plan_command", self.nodes.plan_command)
        graph.add_node("wait_for_approval", self.nodes.wait_for_approval)
        graph.add_node("execute_command", self.nodes.execute_command)
        graph.add_node("verify_command", self.nodes.verify_command)
        graph.add_node("respond_command", self.nodes.respond_command)
        graph.add_node("finalize_command_verifier_outcome", self.nodes.finalize_command_verifier_outcome)
        graph.add_node("advance_step", self.nodes.advance_step)

        graph.add_edge(START, "ingest_request")
        graph.add_edge("ingest_request", "classify_request")
        graph.add_edge("classify_request", "plan_runtime")
        graph.add_edge("plan_runtime", "route_request")
        graph.add_conditional_edges(
            "route_request",
            lambda state: state["route"],
            {
                "inquiry": "answer_inquiry",
                "query": "prepare_query",
                "command": "plan_command",
            },
        )
        graph.add_edge("answer_inquiry", END)
        graph.add_conditional_edges(
            "prepare_query",
            lambda state: (
                "execute_query"
                if state.get("request_status") not in {"failed", "input_required", "ambiguous"}
                else "complete"
            ),
            {
                "execute_query": "execute_query",
                "complete": END,
            },
        )
        graph.add_edge("execute_query", "verify_query")
        graph.add_conditional_edges(
            "verify_query",
            lambda state: state["verifier_route"],
            {
                "retry": "execute_query",
                "success": "advance_step",
                "clarify": "finalize_query_verifier_outcome",
                "escalate": "finalize_query_verifier_outcome",
                "stop": "finalize_query_verifier_outcome",
            },
        )
        graph.add_edge("interpret_result", END)
        graph.add_edge("finalize_query_verifier_outcome", END)
        graph.add_conditional_edges(
            "plan_command",
            lambda state: "wait_for_approval" if state.get("request_status") == "pending_approval" else "complete",
            {
                "wait_for_approval": "wait_for_approval",
                "complete": END,
            },
        )
        graph.add_conditional_edges(
            "wait_for_approval",
            lambda state: "approved" if state.get("approval_granted") else "rejected",
            {
                "approved": "execute_command",
                "rejected": END,
            },
        )
        graph.add_edge("execute_command", "verify_command")
        graph.add_conditional_edges(
            "verify_command",
            lambda state: state["verifier_route"],
            {
                "retry": "execute_command",
                "success": "advance_step",
                "clarify": "finalize_command_verifier_outcome",
                "escalate": "finalize_command_verifier_outcome",
                "stop": "finalize_command_verifier_outcome",
            },
        )
        graph.add_conditional_edges(
            "advance_step",
            _route_after_advance_step,
            {
                "next_command": "execute_command",
                "next_query": "execute_query",
                "done_command": "respond_command",
                "done_query": "interpret_result",
            },
        )
        graph.add_edge("respond_command", END)
        graph.add_edge("finalize_command_verifier_outcome", END)

        return graph.compile(checkpointer=checkpointer)
