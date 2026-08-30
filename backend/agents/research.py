from datetime import date, timedelta

from langchain_core.messages import HumanMessage, SystemMessage

from backend.llm import content_engine
from backend.prompts import RESEARCH_SYNTHESIS_PROMPT
from backend.schemas import ResearchBundle
from backend.services.tavily import perform_web_lookup
from backend.state import BlogWorkflowState
from backend.utils import safe_parse_date


def research_agent(state: BlogWorkflowState) -> dict:
    search_terms = state.get("search_queries", [])[:10]
    raw_search_data = []

    for query in search_terms:
        raw_search_data.extend(
            perform_web_lookup(query=query, max_results=6)
        )

    if not raw_search_data:
        return {"collected_sources": []}

    extraction_chain = content_engine.with_structured_output(ResearchBundle)

    curated_sources = extraction_chain.invoke(
        [
            SystemMessage(content=RESEARCH_SYNTHESIS_PROMPT),
            HumanMessage(
                content=(
                    f"Current Date: {state['current_date']}\n\n"
                    f"Raw Search Data:\n{raw_search_data}"
                )
            ),
        ]
    )

    unique_sources = {}

    for source in curated_sources.items:
        if source.url:
            unique_sources[source.url] = source

    return {"collected_sources": list(unique_sources.values())}


def filter_recent_sources(state: BlogWorkflowState) -> dict:
    strategy = state.get("routing_strategy", "closed_book")

    if strategy != "open_book":
        return {
            "collected_sources": state.get("collected_sources", []),
        }

    today = date.fromisoformat(state["current_date"])
    cutoff = today - timedelta(days=state["freshness_window"])
    filtered = []

    for source in state.get("collected_sources", []):
        published = safe_parse_date(source.published_date)

        if published and published >= cutoff:
            filtered.append(source)

    return {"collected_sources": filtered}
