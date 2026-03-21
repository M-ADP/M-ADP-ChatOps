from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from chatops.graph.nodes import WorkflowNodes
from chatops.graph.state import GraphState


class GraphWorkflow:
    def __init__(self, nodes: WorkflowNodes) -> None:
        self.nodes = nodes

    def compile(self):
        graph = StateGraph(GraphState)
        graph.add_node("ingest_request", self.nodes.ingest_request)
        graph.add_node("classify_request", self.nodes.classify_request)
        graph.add_node("route_request", self.nodes.route_request)
        graph.add_node("answer_inquiry", self.nodes.answer_inquiry)
        graph.add_node("prepare_query", self.nodes.prepare_query)
        graph.add_node("execute_query", self.nodes.execute_query)
        graph.add_node("interpret_result", self.nodes.interpret_result)
        graph.add_node("plan_command", self.nodes.plan_command)
        graph.add_node("wait_for_approval", self.nodes.wait_for_approval)
        graph.add_node("resume_after_approval", self.nodes.resume_after_approval)
        graph.add_node("execute_command", self.nodes.execute_command)
        graph.add_node("respond_command", self.nodes.respond_command)

        graph.add_edge(START, "ingest_request")
        graph.add_edge("ingest_request", "classify_request")
        graph.add_edge("classify_request", "route_request")
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
        graph.add_edge("prepare_query", "execute_query")
        graph.add_edge("execute_query", "interpret_result")
        graph.add_edge("interpret_result", END)
        graph.add_edge("plan_command", "wait_for_approval")
        graph.add_edge("wait_for_approval", END)

        return graph.compile()
