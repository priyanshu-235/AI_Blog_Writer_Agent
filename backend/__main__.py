from backend.graph import blog_writer_app
from backend.state import initial_workflow_state

if __name__ == "__main__":
    result = blog_writer_app.invoke(
        initial_workflow_state("LangGraph Multi Agent Systems")
    )
    print(result["final_markdown"])
