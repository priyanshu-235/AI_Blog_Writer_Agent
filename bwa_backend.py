from __future__ import annotations

import os
import re
import operator

from pathlib import Path
from datetime import date, timedelta

from typing import (
    TypedDict,
    List,
    Optional,
    Literal,
    Annotated,
)

from dotenv import load_dotenv

from pydantic import BaseModel, Field

from langgraph.graph import (
    StateGraph,
    START,
    END,
)

from langgraph.types import Send

from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
)

from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# ==========================================================
# CONFIGURATION
# ==========================================================

TEXT_MODEL = os.getenv(
    "BLOG_TEXT_MODEL",
    "gemini-2.5-flash",
)

IMAGE_MODEL = os.getenv(
    "BLOG_IMAGE_MODEL",
    "gemini-2.5-flash-image",
)

# ==========================================================
# PRIMARY LLM
# ==========================================================

content_engine = ChatGoogleGenerativeAI(
    model=TEXT_MODEL,
    temperature=0.3,
)

# ==========================================================
# CONTENT TASK SCHEMA
# ==========================================================

class SectionBlueprint(BaseModel):
    section_id: int

    heading: str

    objective: str = Field(
        ...,
        description="What should the reader learn?"
    )

    key_points: List[str] = Field(
        ...,
        min_length=3,
        max_length=6,
    )

    target_length: int

    labels: List[str] = Field(
        default_factory=list
    )

    research_required: bool = False

    citations_required: bool = False

    code_required: bool = False


# ==========================================================
# BLOG OUTLINE
# ==========================================================

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

    restrictions: List[str] = Field(
        default_factory=list
    )

    sections: List[SectionBlueprint]


# ==========================================================
# WEB RESEARCH ITEM
# ==========================================================

class SourceRecord(BaseModel):
    title: str

    url: str

    snippet: Optional[str] = None

    source_name: Optional[str] = None

    published_date: Optional[str] = None


class ResearchBundle(BaseModel):
    items: List[SourceRecord] = Field(
        default_factory=list
    )


# ==========================================================
# ROUTER OUTPUT
# ==========================================================

class RoutingDecision(BaseModel):
    research_needed: bool

    strategy: Literal[
        "closed_book",
        "hybrid",
        "open_book",
    ]

    explanation: str

    search_queries: List[str] = Field(
        default_factory=list
    )

    results_per_query: int = 5


# ==========================================================
# IMAGE PLANNING
# ==========================================================

class DiagramRequest(BaseModel):
    placeholder: str

    filename: str

    alt_text: str

    caption: str

    generation_prompt: str

    size: Literal[
        "1024x1024",
        "1024x1536",
        "1536x1024",
    ] = "1024x1024"

    quality: Literal[
        "low",
        "medium",
        "high",
    ] = "medium"


class DiagramPlan(BaseModel):
    markdown_with_slots: str

    diagrams: List[DiagramRequest] = Field(
        default_factory=list
    )


# ==========================================================
# GLOBAL WORKFLOW STATE
# ==========================================================

class BlogWorkflowState(TypedDict):
    topic: str

    routing_strategy: str

    research_needed: bool

    search_queries: List[str]

    collected_sources: List[SourceRecord]

    blog_outline: Optional[BlogBlueprint]

    current_date: str

    freshness_window: int

    generated_sections: Annotated[
        List[tuple[int, str]],
        operator.add,
    ]

    merged_markdown: str

    markdown_with_image_slots: str

    planned_diagrams: List[dict]

    final_markdown: str


# ==========================================================
# UTILITIES
# ==========================================================

def slugify(text: str) -> str:
    value = text.strip().lower()

    value = re.sub(
        r"[^a-z0-9 _-]+",
        "",
        value,
    )

    value = re.sub(
        r"\s+",
        "_",
        value,
    ).strip("_")

    return value or "blog"


def safe_parse_date(
    value: Optional[str],
) -> Optional[date]:
    if not value:
        return None

    try:
        return date.fromisoformat(
            value[:10]
        )
    except Exception:
        return None
    
# ==========================================================
# ROUTER PROMPT
# ==========================================================

ROUTING_SYSTEM_PROMPT = """
You are the routing intelligence for an AI blog writing system.

Your task is to decide whether external web research is needed.

Modes:

closed_book:
- Evergreen concepts
- Stable technical knowledge
- No web research required

hybrid:
- Mostly evergreen
- Requires recent examples, tools, libraries, models, benchmarks

open_book:
- News
- Weekly roundups
- Pricing
- Policies
- Product launches
- Recent events

Rules:

If research is needed:
- Produce 3 to 10 highly specific search queries
- Queries should maximize signal and minimize noise

Output must follow the RoutingDecision schema exactly.
"""
def routing_agent(
    state: BlogWorkflowState,
) -> dict:

    routing_chain = (
        content_engine
        .with_structured_output(
            RoutingDecision
        )
    )

    decision = routing_chain.invoke(
        [
            SystemMessage(
                content=ROUTING_SYSTEM_PROMPT
            ),
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
def routing_decision(
    state: BlogWorkflowState,
) -> str:

    if state["research_needed"]:
        return "research"

    return "planner"
def perform_web_lookup(
    query: str,
    max_results: int = 5,
) -> List[dict]:

    if not os.getenv(
        "TAVILY_API_KEY"
    ):
        return []

    try:
        from langchain_community.tools.tavily_search import (
            TavilySearchResults,
        )

        search_tool = TavilySearchResults(
            max_results=max_results
        )

        raw_results = search_tool.invoke(
            {"query": query}
        )

        cleaned = []

        for item in raw_results or []:

            cleaned.append(
                {
                    "title":
                        item.get("title", ""),

                    "url":
                        item.get("url", ""),

                    "snippet":
                        item.get("content")
                        or item.get("snippet")
                        or "",

                    "published_date":
                        item.get("published_date")
                        or item.get("published_at"),

                    "source_name":
                        item.get("source"),
                }
            )

        return cleaned

    except Exception:
        return []
    
RESEARCH_SYNTHESIS_PROMPT = """
You are a research curator.

You receive raw search results.

Your job:

- Keep only relevant sources
- Remove duplicates
- Remove low quality results
- Remove sources without URLs
- Keep snippets concise
- Preserve publication dates when available

Output must follow ResearchBundle schema.
"""
def research_agent(
    state: BlogWorkflowState,
) -> dict:

    search_terms = (
        state.get(
            "search_queries",
            [],
        )[:10]
    )

    raw_search_data = []

    for query in search_terms:

        raw_search_data.extend(
            perform_web_lookup(
                query=query,
                max_results=6,
            )
        )

    if not raw_search_data:
        return {
            "collected_sources": []
        }

    extraction_chain = (
        content_engine
        .with_structured_output(
            ResearchBundle
        )
    )

    curated_sources = extraction_chain.invoke(
        [
            SystemMessage(
                content=(
                    RESEARCH_SYNTHESIS_PROMPT
                )
            ),
            HumanMessage(
                content=(
                    f"Current Date: "
                    f"{state['current_date']}\n\n"
                    f"Raw Search Data:\n"
                    f"{raw_search_data}"
                )
            ),
        ]
    )

    unique_sources = {}

    for source in curated_sources.items:

        if source.url:
            unique_sources[
                source.url
            ] = source

    final_sources = list(
        unique_sources.values()
    )

    return {
        "collected_sources":
            final_sources
    }
def filter_recent_sources(
    state: BlogWorkflowState,
) -> dict:

    strategy = state.get(
        "routing_strategy",
        "closed_book",
    )

    if strategy != "open_book":

        return {
            "collected_sources":
                state.get(
                    "collected_sources",
                    [],
                )
        }

    today = date.fromisoformat(
        state["current_date"]
    )

    cutoff = (
        today
        - timedelta(
            days=state[
                "freshness_window"
            ]
        )
    )

    filtered = []

    for source in state.get(
        "collected_sources",
        [],
    ):

        published = safe_parse_date(
            source.published_date
        )

        if (
            published
            and published >= cutoff
        ):
            filtered.append(source)

    return {
        "collected_sources":
            filtered
    }
def research_completed(
    state: BlogWorkflowState,
) -> str:

    return "planner"
# ==========================================================
# BLOG PLANNER
# ==========================================================

PLANNING_SYSTEM_PROMPT = """
You are an elite technical writer.

Create a complete blog structure.

Requirements:

- 5 to 9 sections
- Each section must have:
    - objective
    - 3 to 6 key points
    - target length

Guidelines:

closed_book:
- Use timeless concepts

hybrid:
- Use provided sources when useful
- Mark those sections as:
    research_required=True
    citations_required=True

open_book:
- Create a news roundup structure
- Focus on events and implications
- Never invent news

Output must match BlogBlueprint exactly.
"""
def planning_agent(
    state: BlogWorkflowState,
) -> dict:

    planner_chain = (
        content_engine
        .with_structured_output(
            BlogBlueprint
        )
    )

    strategy = state.get(
        "routing_strategy",
        "closed_book"
    )

    evidence = state.get(
        "collected_sources",
        []
    )

    forced_category = (
        "news_roundup"
        if strategy == "open_book"
        else None
    )

    generated_outline = planner_chain.invoke(
        [
            SystemMessage(
                content=PLANNING_SYSTEM_PROMPT
            ),
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
        generated_outline.category = (
            forced_category
        )

    return {
        "blog_outline":
            generated_outline
    }
def distribute_sections(
    state: BlogWorkflowState,
):

    outline = state["blog_outline"]

    assert outline is not None

    return [
        Send(
            "section_writer",
            {
                "section":
                    section.model_dump(),

                "topic":
                    state["topic"],

                "strategy":
                    state[
                        "routing_strategy"
                    ],

                "current_date":
                    state[
                        "current_date"
                    ],

                "outline":
                    outline.model_dump(),

                "sources":
                    [
                        item.model_dump()
                        for item in state.get(
                            "collected_sources",
                            []
                        )
                    ],
            },
        )
        for section in outline.sections
    ]
SECTION_AUTHOR_PROMPT = """
You are a senior developer advocate.

Write ONE blog section.

Requirements:

- Cover every key point.
- Stay within ±15% of target length.
- Output only markdown.

Rules:

Start with:

## Section Title

If citations are required:
- Cite provided URLs.

If code_required:
- Include a concise code snippet.

For open_book:
- Never invent facts.
- Use only provided sources.
- If evidence is missing:
  write:
  "Not found in provided sources."
"""
def section_writer(
    payload: dict,
) -> dict:

    section = SectionBlueprint(
        **payload["section"]
    )

    outline = BlogBlueprint(
        **payload["outline"]
    )

    sources = [
        SourceRecord(**item)
        for item in payload.get(
            "sources",
            []
        )
    ]

    key_points_text = (
        "\n- "
        + "\n- ".join(
            section.key_points
        )
    )

    source_text = "\n".join(
        (
            f"- {src.title}"
            f" | {src.url}"
            f" | {src.published_date}"
        )
        for src in sources[:25]
    )

    generated_section = (
        content_engine.invoke(
            [
                SystemMessage(
                    content=
                    SECTION_AUTHOR_PROMPT
                ),
                HumanMessage(
                    content=(
                        f"Blog Title: "
                        f"{outline.title}\n"

                        f"Audience: "
                        f"{outline.audience}\n"

                        f"Tone: "
                        f"{outline.tone}\n"

                        f"Category: "
                        f"{outline.category}\n\n"

                        f"Topic: "
                        f"{payload['topic']}\n"

                        f"Strategy: "
                        f"{payload['strategy']}\n\n"

                        f"Section Heading: "
                        f"{section.heading}\n"

                        f"Objective: "
                        f"{section.objective}\n"

                        f"Target Length: "
                        f"{section.target_length}\n"

                        f"Research Required: "
                        f"{section.research_required}\n"

                        f"Citations Required: "
                        f"{section.citations_required}\n"

                        f"Code Required: "
                        f"{section.code_required}\n\n"

                        f"Key Points:\n"
                        f"{key_points_text}\n\n"

                        f"Available Sources:\n"
                        f"{source_text}"
                    )
                ),
            ]
        )
        .content
        .strip()
    )

    return {
        "generated_sections":
        [
            (
                section.section_id,
                generated_section
            )
        ]
    }
def combine_sections(
    state: BlogWorkflowState,
) -> dict:

    outline = state[
        "blog_outline"
    ]

    if outline is None:
        raise ValueError(
            "Missing blog outline."
        )

    ordered_content = [
        content
        for _, content
        in sorted(
            state[
                "generated_sections"
            ],
            key=lambda x: x[0]
        )
    ]

    full_article = "\n\n".join(
        ordered_content
    )

    markdown_document = (
        f"# {outline.title}\n\n"
        f"{full_article}\n"
    )

    return {
        "merged_markdown":
            markdown_document
    }
DIAGRAM_PLANNER_PROMPT = """
You are a technical editor.

Determine whether diagrams would improve this blog.

Rules:

- Maximum 3 diagrams
- No decorative images
- Only diagrams that improve understanding
- Use placeholders:

[[DIAGRAM_1]]
[[DIAGRAM_2]]
[[DIAGRAM_3]]

Examples:

- System architecture
- Data flow
- API lifecycle
- Training pipeline
- Comparison matrix
- Deployment architecture

If no diagrams are needed:

return:
    diagrams=[]
    markdown_with_slots=input_markdown

Output must follow DiagramPlan.
"""
def diagram_planner(
    state: BlogWorkflowState,
) -> dict:

    outline = state["blog_outline"]

    planner = (
        content_engine
        .with_structured_output(
            DiagramPlan
        )
    )

    plan = planner.invoke(
        [
            SystemMessage(
                content=
                DIAGRAM_PLANNER_PROMPT
            ),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n"
                    f"Category: {outline.category}\n\n"
                    f"{state['merged_markdown']}"
                )
            ),
        ]
    )

    return {
        "markdown_with_image_slots":
            plan.markdown_with_slots,

        "planned_diagrams":
            [
                diagram.model_dump()
                for diagram
                in plan.diagrams
            ],
    }
def create_diagram_bytes(
    prompt: str,
) -> bytes:

    from google import genai
    from google.genai import types

    api_key = os.getenv(
        "GOOGLE_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY missing."
        )

    client = genai.Client(
        api_key=api_key
    )

    response = (
        client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[
                    "IMAGE"
                ]
            ),
        )
    )

    image_parts = (
        getattr(response, "parts", None)
    )

    if (
        not image_parts
        and getattr(
            response,
            "candidates",
            None
        )
    ):
        image_parts = (
            response
            .candidates[0]
            .content
            .parts
        )

    if not image_parts:
        raise RuntimeError(
            "Gemini returned no image."
        )

    for part in image_parts:

        inline_data = getattr(
            part,
            "inline_data",
            None,
        )

        if (
            inline_data
            and getattr(
                inline_data,
                "data",
                None,
            )
        ):
            return inline_data.data

    raise RuntimeError(
        "No image bytes found."
    )
def ensure_diagram_folder() -> Path:

    directory = Path(
        "generated_diagrams"
    )

    directory.mkdir(
        exist_ok=True
    )

    return directory
def render_diagrams(
    state: BlogWorkflowState,
) -> dict:

    outline = state["blog_outline"]

    markdown = (
        state.get(
            "markdown_with_image_slots"
        )
        or
        state[
            "merged_markdown"
        ]
    )

    diagrams = (
        state.get(
            "planned_diagrams",
            [],
        )
        or []
    )

    if not diagrams:

        filename = (
            f"{slugify(outline.title)}.md"
        )

        Path(filename).write_text(
            markdown,
            encoding="utf-8",
        )

        return {
            "final_markdown":
                markdown
        }

    output_dir = (
        ensure_diagram_folder()
    )

    for diagram in diagrams:

        placeholder = (
            diagram[
                "placeholder"
            ]
        )

        image_name = (
            diagram[
                "filename"
            ]
        )

        output_path = (
            output_dir
            / image_name
        )

        if not output_path.exists():

            try:

                image_bytes = (
                    create_diagram_bytes(
                        diagram[
                            "generation_prompt"
                        ]
                    )
                )

                output_path.write_bytes(
                    image_bytes
                )

            except Exception as exc:

                fallback = (
                    f"\n"
                    f"> Diagram generation failed\n\n"
                    f"> Caption: "
                    f"{diagram['caption']}\n\n"
                    f"> Error: "
                    f"{exc}\n"
                )

                markdown = (
                    markdown.replace(
                        placeholder,
                        fallback,
                    )
                )

                continue

        image_markdown = (
            f"![{diagram['alt_text']}]"
            f"(generated_diagrams/"
            f"{image_name})\n"
            f"*{diagram['caption']}*"
        )

        markdown = (
            markdown.replace(
                placeholder,
                image_markdown,
            )
        )

    filename = (
        f"{slugify(outline.title)}.md"
    )

    Path(filename).write_text(
        markdown,
        encoding="utf-8",
    )

    return {
        "final_markdown":
            markdown
    }
def finalize_blog(
    state: BlogWorkflowState,
) -> dict:

    return {
        "final_markdown":
            state[
                "final_markdown"
            ]
    }
image_pipeline = StateGraph(
    BlogWorkflowState
)

image_pipeline.add_node(
    "diagram_planner",
    diagram_planner,
)

image_pipeline.add_node(
    "render_diagrams",
    render_diagrams,
)

image_pipeline.add_node(
    "finalize_blog",
    finalize_blog,
)

image_pipeline.add_edge(
    START,
    "diagram_planner",
)

image_pipeline.add_edge(
    "diagram_planner",
    "render_diagrams",
)

image_pipeline.add_edge(
    "render_diagrams",
    "finalize_blog",
)

image_pipeline.add_edge(
    "finalize_blog",
    END,
)

diagram_subgraph = (
    image_pipeline.compile()
)
workflow = StateGraph(
    BlogWorkflowState
)
workflow.add_node(
    "routing_agent",
    routing_agent,
)

workflow.add_node(
    "research_agent",
    research_agent,
)

workflow.add_node(
    "filter_recent_sources",
    filter_recent_sources,
)

workflow.add_node(
    "planning_agent",
    planning_agent,
)

workflow.add_node(
    "section_writer",
    section_writer,
)

workflow.add_node(
    "combine_sections",
    combine_sections,
)

workflow.add_node(
    "diagram_pipeline",
    diagram_subgraph,
)
workflow.add_edge(
    START,
    "routing_agent",
)
workflow.add_conditional_edges(
    "routing_agent",
    routing_decision,
    {
        "research":
            "research_agent",

        "planner":
            "planning_agent",
    },
)
workflow.add_edge(
    "research_agent",
    "filter_recent_sources",
)

workflow.add_edge(
    "filter_recent_sources",
    "planning_agent",
)
workflow.add_conditional_edges(
    "planning_agent",
    distribute_sections,
    [
        "section_writer"
    ],
)
workflow.add_edge(
    "section_writer",
    "combine_sections",
)
generated_sections:Annotated[
    List[tuple[int, str]],
    operator.add,
]
workflow.add_edge(
    "combine_sections",
    "diagram_pipeline",
)
workflow.add_edge(
    "diagram_pipeline",
    END,
)
blog_writer_app = workflow.compile()
if __name__ == "__main__":

    result = blog_writer_app.invoke(
        {
            "topic":
                "LangGraph Multi Agent Systems",

            "routing_strategy":
                "",

            "research_needed":
                False,

            "search_queries":
                [],

            "collected_sources":
                [],

            "blog_outline":
                None,

            "current_date":
                date.today().isoformat(),

            "freshness_window":
                7,

            "generated_sections":
                [],

            "merged_markdown":
                "",

            "markdown_with_image_slots":
                "",

            "planned_diagrams":
                [],

            "final_markdown":
                "",
        }
    )

    print(
        result[
            "final_markdown"
        ]
    )