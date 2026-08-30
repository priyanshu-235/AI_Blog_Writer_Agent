from langchain_core.messages import HumanMessage, SystemMessage

from backend.llm import content_engine
from backend.prompts import SECTION_AUTHOR_PROMPT
from backend.schemas import BlogBlueprint, SectionBlueprint, SourceRecord
from backend.state import BlogWorkflowState


def section_writer(payload: dict) -> dict:
    section = SectionBlueprint(**payload["section"])
    outline = BlogBlueprint(**payload["outline"])
    sources = [
        SourceRecord(**item) for item in payload.get("sources", [])
    ]

    key_points_text = "\n- " + "\n- ".join(section.key_points)
    source_text = "\n".join(
        f"- {src.title} | {src.url} | {src.published_date}"
        for src in sources[:25]
    )

    generated_section = (
        content_engine.invoke(
            [
                SystemMessage(content=SECTION_AUTHOR_PROMPT),
                HumanMessage(
                    content=(
                        f"Blog Title: {outline.title}\n"
                        f"Audience: {outline.audience}\n"
                        f"Tone: {outline.tone}\n"
                        f"Category: {outline.category}\n\n"
                        f"Topic: {payload['topic']}\n"
                        f"Strategy: {payload['strategy']}\n\n"
                        f"Section Heading: {section.heading}\n"
                        f"Objective: {section.objective}\n"
                        f"Target Length: {section.target_length}\n"
                        f"Research Required: {section.research_required}\n"
                        f"Citations Required: {section.citations_required}\n"
                        f"Code Required: {section.code_required}\n\n"
                        f"Key Points:\n{key_points_text}\n\n"
                        f"Available Sources:\n{source_text}"
                    )
                ),
            ]
        )
        .content
        .strip()
    )

    return {
        "generated_sections": [
            (section.section_id, generated_section),
        ]
    }


def combine_sections(state: BlogWorkflowState) -> dict:
    outline = state["blog_outline"]

    if outline is None:
        raise ValueError("Missing blog outline.")

    ordered_content = [
        content
        for _, content in sorted(
            state["generated_sections"],
            key=lambda x: x[0],
        )
    ]

    markdown_document = f"# {outline.title}\n\n" + "\n\n".join(ordered_content) + "\n"
    return {"merged_markdown": markdown_document}
