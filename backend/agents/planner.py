from langgraph.types import Send
from langchain_core.messages import HumanMessage, SystemMessage

from backend.llm import content_engine
from backend.prompts import PLANNING_SYSTEM_PROMPT
from backend.schemas import BlogBlueprint
from backend.state import BlogWorkflowState


def planning_agent(state: BlogWorkflowState) -> dict:
    planner_chain = content_engine.with_structured_output(BlogBlueprint)
    strategy = state.get("routing_strategy", "closed_book")
    evidence = state.get("collected_sources", [])
    forced_category = "news_roundup" if strategy == "open_book" else None

    generated_outline = planner_chain.invoke(
        [
            SystemMessage(content=PLANNING_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n"
                    f"Strategy: {strategy}\n"
                    f"Current Date: {state['current_date']}\n\n"
                    f"Sources:\n"
                    f"{[s.model_dump() for s in evidence][:20]}"
                )
            ),
        ]
    )

    if forced_category:
        generated_outline.category = forced_category

    return {"blog_outline": generated_outline}


def distribute_sections(state: BlogWorkflowState):
    outline = state["blog_outline"]
    assert outline is not None

    return [
        Send(
            "section_writer",
            {
                "section": section.model_dump(),
                "topic": state["topic"],
                "strategy": state["routing_strategy"],
                "current_date": state["current_date"],
                "outline": outline.model_dump(),
                "sources": [
                    item.model_dump()
                    for item in state.get("collected_sources", [])
                ],
            },
        )
        for section in outline.sections
    ]
