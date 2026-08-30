from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, List, Optional, TypedDict

from backend.schemas import BlogBlueprint, SourceRecord


class BlogWorkflowState(TypedDict):
    topic: str
    routing_strategy: str
    research_needed: bool
    search_queries: List[str]
    collected_sources: List[SourceRecord]
    blog_outline: Optional[BlogBlueprint]
    current_date: str
    freshness_window: int
    generated_sections: Annotated[List[tuple[int, str]], operator.add]
    merged_markdown: str
    markdown_with_image_slots: str
    planned_diagrams: List[dict]
    diagram_assets: List[dict]
    final_markdown: str


def initial_workflow_state(
    topic: str,
    current_date: Optional[str] = None,
) -> BlogWorkflowState:
    return {
        "topic": topic,
        "routing_strategy": "",
        "research_needed": False,
        "search_queries": [],
        "collected_sources": [],
        "blog_outline": None,
        "current_date": current_date or date.today().isoformat(),
        "freshness_window": 7,
        "generated_sections": [],
        "merged_markdown": "",
        "markdown_with_image_slots": "",
        "planned_diagrams": [],
        "diagram_assets": [],
        "final_markdown": "",
    }
