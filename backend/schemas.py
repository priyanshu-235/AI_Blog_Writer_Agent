from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class SectionBlueprint(BaseModel):
    section_id: int
    heading: str
    objective: str = Field(..., description="What should the reader learn?")
    key_points: List[str] = Field(..., min_length=3, max_length=6)
    target_length: int
    labels: List[str] = Field(default_factory=list)
    research_required: bool = False
    citations_required: bool = False
    code_required: bool = False


class BlogBlueprint(BaseModel):
    title: str
    audience: str
    tone: str
    category: Literal[
        "explainer",
        "tutorial",
        "comparison",
        "news_roundup",
        "system_design",
    ] = "explainer"
    restrictions: List[str] = Field(default_factory=list)
    sections: List[SectionBlueprint]


class SourceRecord(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None
    source_name: Optional[str] = None
    published_date: Optional[str] = None


class ResearchBundle(BaseModel):
    items: List[SourceRecord] = Field(default_factory=list)


class RoutingDecision(BaseModel):
    research_needed: bool
    strategy: Literal["closed_book", "hybrid", "open_book"]
    explanation: str
    search_queries: List[str] = Field(default_factory=list)
    results_per_query: int = 5


class DiagramRequest(BaseModel):
    placeholder: str
    filename: str
    alt_text: str
    caption: str
    generation_prompt: str
    size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    quality: Literal["low", "medium", "high"] = "medium"


class DiagramPlan(BaseModel):
    markdown_with_slots: str
    diagrams: List[DiagramRequest] = Field(default_factory=list)
