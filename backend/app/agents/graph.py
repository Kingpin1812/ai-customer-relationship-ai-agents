from functools import lru_cache

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents import nodes
from app.agents.checkpointer import get_checkpointer
from app.agents.state import WorkflowState
from app.services.approvals.snapshot import has_sensitive_actions

_PIPELINE = [
    "resolve_customer",
    "create_invoice",
    "generate_report",
    "draft_email",
    "request_approval",
]


def _applies(node: str, plan: dict) -> bool:
    actions = set(plan["actions"])
    return {
        "resolve_customer": bool(actions & {"invoice", "crm_note", "email"}),
        "create_invoice": "invoice" in actions,
        "generate_report": "report" in actions,
        "draft_email": "email" in actions,
        "request_approval": has_sensitive_actions(plan),
    }[node]


def _next_after(current: str | None):
    start = _PIPELINE.index(current) + 1 if current else 0

    def route(state: WorkflowState) -> str:
        for node in _PIPELINE[start:]:
            if _applies(node, state["plan"]):
                return node
        return "complete"

    return route


def await_approval(state: WorkflowState) -> dict:
    """The pause. Only a recorded decision, read back by the runner, resumes this."""
    resume = interrupt({"approval_id": state.get("approval_id")})
    return {"approval_id": resume["approval_id"], "decision": resume["decision"]}


def _after_decision(state: WorkflowState) -> str:
    return "execute_actions" if state.get("decision") == "approved" else "stop_after_decision"


def _after_execution(state: WorkflowState) -> str:
    return "request_approval" if state.get("needs_new_approval") else "complete"


def _build():
    graph = StateGraph(WorkflowState)
    graph.add_node("plan", nodes.plan_node)
    graph.add_node("resolve_customer", nodes.resolve_customer_node)
    graph.add_node("create_invoice", nodes.create_invoice_node)
    graph.add_node("generate_report", nodes.generate_report_node)
    graph.add_node("draft_email", nodes.draft_email_node)
    graph.add_node("request_approval", nodes.request_approval_node)
    graph.add_node("await_approval", await_approval)
    graph.add_node("execute_actions", nodes.execute_actions_node)
    graph.add_node("complete", nodes.complete_node)
    graph.add_node("stop_after_decision", nodes.stop_node)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", _next_after(None))
    for node in _PIPELINE[:-1]:
        graph.add_conditional_edges(node, _next_after(node))
    graph.add_edge("request_approval", "await_approval")
    graph.add_conditional_edges("await_approval", _after_decision)
    graph.add_conditional_edges("execute_actions", _after_execution)
    graph.add_edge("complete", END)
    graph.add_edge("stop_after_decision", END)
    return graph.compile(checkpointer=get_checkpointer())


@lru_cache
def get_graph():
    return _build()


def reset_graph_for_tests() -> None:
    get_graph.cache_clear()
