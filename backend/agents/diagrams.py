from typing import List

from langchain_core.messages import HumanMessage, SystemMessage

from backend.llm import content_engine
from backend.prompts import DIAGRAM_PLANNER_PROMPT
from backend.schemas import DiagramPlan
from backend.services.cloudinary import upload_diagram_to_cloudinary
from backend.services.gemini_image import create_diagram_bytes
from backend.state import BlogWorkflowState
from backend.utils import slugify


def diagram_planner(state: BlogWorkflowState) -> dict:
    outline = state["blog_outline"]
    planner = content_engine.with_structured_output(DiagramPlan)

    plan = planner.invoke(
        [
            SystemMessage(content=DIAGRAM_PLANNER_PROMPT),
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
        "markdown_with_image_slots": plan.markdown_with_slots,
        "planned_diagrams": [diagram.model_dump() for diagram in plan.diagrams],
    }


def render_diagrams(state: BlogWorkflowState) -> dict:
    outline = state["blog_outline"]
    markdown = state.get("markdown_with_image_slots") or state["merged_markdown"]
    diagrams = state.get("planned_diagrams", []) or []
    assets: List[dict] = []

    if not diagrams:
        return {
            "final_markdown": markdown,
            "diagram_assets": assets,
        }

    blog_slug = slugify(outline.title if outline else state["topic"])
    folder = f"blog-writing-agent/{blog_slug}"

    for diagram in diagrams:
        placeholder = diagram["placeholder"]
        image_name = diagram["filename"]

        try:
            image_bytes = create_diagram_bytes(diagram["generation_prompt"])
            upload = upload_diagram_to_cloudinary(
                image_bytes=image_bytes,
                folder=folder,
                public_id=image_name,
            )
        except Exception as exc:
            fallback = (
                f"\n> Diagram generation failed\n\n"
                f"> Caption: {diagram['caption']}\n\n"
                f"> Error: {exc}\n"
            )
            markdown = markdown.replace(placeholder, fallback)
            continue

        image_url = upload["secure_url"]

        assets.append(
            {
                "filename": image_name,
                "url": image_url,
                "secure_url": image_url,
                "cloudinary_public_id": upload["public_id"],
                "alt_text": diagram["alt_text"],
                "caption": diagram["caption"],
                "resource_type": upload.get("resource_type", "image"),
            }
        )

        image_markdown = (
            f"![{diagram['alt_text']}]({image_url})\n"
            f"*{diagram['caption']}*"
        )
        markdown = markdown.replace(placeholder, image_markdown)

    return {
        "final_markdown": markdown,
        "diagram_assets": assets,
    }


def finalize_blog(state: BlogWorkflowState) -> dict:
    return {"final_markdown": state["final_markdown"]}
