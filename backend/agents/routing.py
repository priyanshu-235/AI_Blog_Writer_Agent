from langchain_core.messages import HumanMessage, SystemMessage

from backend.llm import content_engine
from backend.prompts import ROUTING_SYSTEM_PROMPT
from backend.schemas import RoutingDecision
from backend.state import BlogWorkflowState


def routing_agent(state: BlogWorkflowState) -> dict:
    routing_chain = content_engine.with_structured_output(RoutingDecision)

    decision = routing_chain.invoke(
        [
            SystemMessage(content=ROUTING_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n"
                    f"Date: {state['current_date']}"
                )
            ),
        ]
    )

    if decision.strategy == "open_book":
        freshness_window = 7
    elif decision.strategy == "hybrid":
        freshness_window = 45
    else:
        freshness_window = 3650

    return {
        "research_needed": decision.research_needed,
        "routing_strategy": decision.strategy,
        "search_queries": decision.search_queries,
        "freshness_window": freshness_window,
    }


def routing_decision(state: BlogWorkflowState) -> str:
    if state["research_needed"]:
        return "research"

    return "planner"
