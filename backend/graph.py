from langgraph.graph import END, START, StateGraph

from backend.agents.diagrams import diagram_planner, finalize_blog, render_diagrams
from backend.agents.planner import distribute_sections, planning_agent
from backend.agents.research import filter_recent_sources, research_agent
from backend.agents.routing import routing_agent, routing_decision
from backend.agents.writer import combine_sections, section_writer
from backend.state import BlogWorkflowState


def build_diagram_subgraph():
    image_pipeline = StateGraph(BlogWorkflowState)
    image_pipeline.add_node("diagram_planner", diagram_planner)
    image_pipeline.add_node("render_diagrams", render_diagrams)
    image_pipeline.add_node("finalize_blog", finalize_blog)
    image_pipeline.add_edge(START, "diagram_planner")
    image_pipeline.add_edge("diagram_planner", "render_diagrams")
    image_pipeline.add_edge("render_diagrams", "finalize_blog")
    image_pipeline.add_edge("finalize_blog", END)
    return image_pipeline.compile()


def build_blog_writer_app():
    workflow = StateGraph(BlogWorkflowState)
    workflow.add_node("routing_agent", routing_agent)
    workflow.add_node("research_agent", research_agent)
    workflow.add_node("filter_recent_sources", filter_recent_sources)
    workflow.add_node("planning_agent", planning_agent)
    workflow.add_node("section_writer", section_writer)
    workflow.add_node("combine_sections", combine_sections)
    workflow.add_node("diagram_pipeline", build_diagram_subgraph())

    workflow.add_edge(START, "routing_agent")
    workflow.add_conditional_edges(
        "routing_agent",
        routing_decision,
        {
            "research": "research_agent",
            "planner": "planning_agent",
        },
    )
    workflow.add_edge("research_agent", "filter_recent_sources")
    workflow.add_edge("filter_recent_sources", "planning_agent")
    workflow.add_conditional_edges(
        "planning_agent",
        distribute_sections,
        ["section_writer"],
    )
    workflow.add_edge("section_writer", "combine_sections")
    workflow.add_edge("combine_sections", "diagram_pipeline")
    workflow.add_edge("diagram_pipeline", END)

    return workflow.compile()


blog_writer_app = build_blog_writer_app()
