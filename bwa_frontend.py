from __future__ import annotations

import json
import re
import zipfile

from io import BytesIO
from pathlib import Path
from datetime import date

from typing import (
    Any,
    Dict,
    List,
    Optional,
    Iterator,
    Tuple,
)

import pandas as pd
import streamlit as st

from bwa_backend import blog_writer_app


# ==========================================================
# HELPERS
# ==========================================================

def slugify(text: str) -> str:

    text = text.strip().lower()

    text = re.sub(
        r"[^a-z0-9 _-]+",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        "_",
        text,
    ).strip("_")

    return text or "blog"


def create_bundle_zip(
    markdown_text: str,
    markdown_filename: str,
    diagram_folder: Path,
) -> bytes:

    buffer = BytesIO()

    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:

        archive.writestr(
            markdown_filename,
            markdown_text.encode(
                "utf-8"
            ),
        )

        if diagram_folder.exists():

            for file in diagram_folder.rglob("*"):

                if file.is_file():

                    archive.write(
                        file,
                        arcname=str(file),
                    )

    return buffer.getvalue()


def create_diagram_zip(
    diagram_folder: Path,
) -> Optional[bytes]:

    if (
        not diagram_folder.exists()
        or
        not diagram_folder.is_dir()
    ):
        return None

    buffer = BytesIO()

    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:

        for file in diagram_folder.rglob("*"):

            if file.is_file():

                archive.write(
                    file,
                    arcname=str(file),
                )

    return buffer.getvalue()


# ==========================================================
# GRAPH STREAMING
# ==========================================================

def run_graph_stream(
    graph,
    inputs: Dict[str, Any],
) -> Iterator[Tuple[str, Any]]:

    try:

        for update in graph.stream(
            inputs,
            stream_mode="updates",
        ):

            yield (
                "updates",
                update,
            )

        final_state = graph.invoke(
            inputs
        )

        yield (
            "final",
            final_state,
        )

        return

    except Exception:
        pass

    try:

        for update in graph.stream(
            inputs,
            stream_mode="values",
        ):

            yield (
                "values",
                update,
            )

        final_state = graph.invoke(
            inputs
        )

        yield (
            "final",
            final_state,
        )

        return

    except Exception:
        pass

    final_state = graph.invoke(
        inputs
    )

    yield (
        "final",
        final_state,
    )


# ==========================================================
# STATE MERGING
# ==========================================================

def merge_state_update(
    current_state: Dict[str, Any],
    payload: Any,
) -> Dict[str, Any]:

    if not isinstance(
        payload,
        dict,
    ):
        return current_state

    if (
        len(payload) == 1
        and isinstance(
            next(
                iter(
                    payload.values()
                )
            ),
            dict,
        )
    ):

        inner = next(
            iter(
                payload.values()
            )
        )

        current_state.update(
            inner
        )

    else:

        current_state.update(
            payload
        )

    return current_state
# ==========================================================
# MARKDOWN IMAGE SUPPORT
# ==========================================================

IMAGE_PATTERN = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)"
)

CAPTION_PATTERN = re.compile(
    r"^\*(?P<caption>.+)\*$"
)


def resolve_image_path(
    source: str,
) -> Path:

    source = (
        source
        .strip()
        .lstrip("./")
    )

    return Path(
        source
    ).resolve()


def render_markdown_content(
    markdown_text: str,
):

    matches = list(
        IMAGE_PATTERN.finditer(
            markdown_text
        )
    )

    if not matches:

        st.markdown(
            markdown_text,
            unsafe_allow_html=False,
        )

        return

    segments = []

    last_index = 0

    for match in matches:

        before = markdown_text[
            last_index:match.start()
        ]

        if before:

            segments.append(
                (
                    "markdown",
                    before,
                )
            )

        alt = (
            match.group("alt")
            or ""
        ).strip()

        source = (
            match.group("src")
            or ""
        ).strip()

        segments.append(
            (
                "image",
                f"{alt}|||{source}",
            )
        )

        last_index = match.end()

    tail = markdown_text[
        last_index:
    ]

    if tail:

        segments.append(
            (
                "markdown",
                tail,
            )
        )

    pointer = 0

    while pointer < len(
        segments
    ):

        segment_type, value = (
            segments[pointer]
        )

        if (
            segment_type
            == "markdown"
        ):

            st.markdown(
                value,
                unsafe_allow_html=False,
            )

            pointer += 1
            continue

        alt_text, image_src = (
            value.split(
                "|||",
                1,
            )
        )

        caption = None

        if (
            pointer + 1
            < len(segments)
            and segments[
                pointer + 1
            ][0]
            == "markdown"
        ):

            next_text = (
                segments[
                    pointer + 1
                ][1]
                .lstrip()
            )

            if next_text.strip():

                first_line = (
                    next_text
                    .splitlines()[0]
                    .strip()
                )

                caption_match = (
                    CAPTION_PATTERN.match(
                        first_line
                    )
                )

                if caption_match:

                    caption = (
                        caption_match.group(
                            "caption"
                        )
                    )

                    remaining = (
                        "\n".join(
                            next_text.splitlines()[1:]
                        )
                    )

                    segments[
                        pointer + 1
                    ] = (
                        "markdown",
                        remaining,
                    )

        if (
            image_src.startswith(
                "http://"
            )
            or image_src.startswith(
                "https://"
            )
        ):

            st.image(
                image_src,
                caption=caption,
                use_container_width=True,
            )

        else:

            image_path = (
                resolve_image_path(
                    image_src
                )
            )

            if image_path.exists():

                st.image(
                    str(image_path),
                    caption=caption,
                    use_container_width=True,
                )

            else:

                st.warning(
                    f"Image not found: {image_src}"
                )

        pointer += 1


# ==========================================================
# BLOG FILES
# ==========================================================

def list_saved_blogs(
) -> List[Path]:

    files = list(
        Path(".").glob(
            "*.md"
        )
    )

    files.sort(
        key=lambda p:
        p.stat().st_mtime,
        reverse=True,
    )

    return files


def read_blog_file(
    path: Path,
) -> str:

    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def extract_blog_title(
    markdown_text: str,
    fallback: str,
) -> str:

    for line in (
        markdown_text.splitlines()
    ):

        if line.startswith("# "):

            title = (
                line[2:]
                .strip()
            )

            return (
                title
                or fallback
            )

    return fallback


# ==========================================================
# PAGE CONFIG
# ==========================================================

st.set_page_config(
    page_title=
    "Gemini Blog Writer",
    layout="wide",
)

st.title(
    "Gemini Blog Writing Agent"
)


# ==========================================================
# SIDEBAR
# ==========================================================

with st.sidebar:

    st.header(
        "Generate Blog"
    )

    topic = st.text_area(
        "Topic",
        height=120,
    )

    current_date = (
        st.date_input(
            "Current Date",
            value=date.today(),
        )
    )

    run_button = st.button(
        "🚀 Generate",
        type="primary",
    )

    st.divider()

    st.subheader(
        "Saved Blogs"
    )

    blog_files = (
        list_saved_blogs()
    )

    selected_blog = None

    if not blog_files:

        st.caption(
            "No saved markdown blogs."
        )

    else:

        labels = []

        label_map = {}

        for file in blog_files[:50]:

            try:

                text = (
                    read_blog_file(
                        file
                    )
                )

                title = (
                    extract_blog_title(
                        text,
                        file.stem,
                    )
                )

            except Exception:

                title = file.stem

            label = (
                f"{title}"
                f" · "
                f"{file.name}"
            )

            labels.append(
                label
            )

            label_map[
                label
            ] = file

        chosen_label = (
            st.radio(
                "Blogs",
                labels,
                label_visibility=
                "collapsed",
            )
        )

        selected_blog = (
            label_map.get(
                chosen_label
            )
        )

        if st.button(
            "📂 Load Blog"
        ):

            if selected_blog:

                markdown_text = (
                    read_blog_file(
                        selected_blog
                    )
                )

                st.session_state[
                    "last_result"
                ] = {
                    "blog_outline":
                        None,

                    "collected_sources":
                        [],

                    "planned_diagrams":
                        [],

                    "final_markdown":
                        markdown_text,
                }


# ==========================================================
# SESSION STATE
# ==========================================================

if (
    "last_result"
    not in st.session_state
):
    st.session_state[
        "last_result"
    ] = None


if (
    "logs"
    not in st.session_state
):
    st.session_state[
        "logs"
    ] = []


runtime_logs: List[
    str
] = []


def log_message(
    message: str,
):

    runtime_logs.append(
        message
    )


# ==========================================================
# TABS
# ==========================================================

(
    tab_outline,
    tab_sources,
    tab_preview,
    tab_diagrams,
    tab_logs,
) = st.tabs(
    [
        "🧩 Outline",
        "🔎 Sources",
        "📝 Preview",
        "🖼️ Diagrams",
        "🧾 Logs",
    ]
)
# ==========================================================
# RUN WORKFLOW
# ==========================================================

if run_button:

    if not topic.strip():

        st.warning(
            "Please enter a topic."
        )

        st.stop()

    workflow_input = {

        "topic":
            topic.strip(),

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
            current_date.isoformat(),

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

    execution_status = st.status(
        "Running workflow...",
        expanded=True,
    )

    progress_panel = st.empty()

    current_state = {}

    previous_node = None

    for (
        event_type,
        payload,
    ) in run_graph_stream(
        blog_writer_app,
        workflow_input,
    ):

        if event_type in (
            "updates",
            "values",
        ):

            node_name = None

            if (
                isinstance(
                    payload,
                    dict,
                )
                and len(payload) == 1
                and isinstance(
                    next(
                        iter(
                            payload.values()
                        )
                    ),
                    dict,
                )
            ):

                node_name = next(
                    iter(
                        payload.keys()
                    )
                )

            if (
                node_name
                and node_name
                != previous_node
            ):

                execution_status.write(
                    f"➡️ {node_name}"
                )

                previous_node = (
                    node_name
                )

            current_state = (
                merge_state_update(
                    current_state,
                    payload,
                )
            )

            progress_summary = {

                "strategy":
                    current_state.get(
                        "routing_strategy"
                    ),

                "research_needed":
                    current_state.get(
                        "research_needed"
                    ),

                "queries":
                    current_state.get(
                        "search_queries",
                        [],
                    )[:5],

                "source_count":
                    len(
                        current_state.get(
                            "collected_sources",
                            [],
                        )
                        or []
                    ),

                "sections_written":
                    len(
                        current_state.get(
                            "generated_sections",
                            [],
                        )
                        or []
                    ),

                "diagram_count":
                    len(
                        current_state.get(
                            "planned_diagrams",
                            [],
                        )
                        or []
                    ),
            }

            progress_panel.json(
                progress_summary
            )

            log_message(
                f"[{event_type}] "
                f"{json.dumps(payload, default=str)[:1000]}"
            )

        elif (
            event_type
            == "final"
        ):

            st.session_state[
                "last_result"
            ] = payload

            execution_status.update(
                label="✅ Complete",
                state="complete",
                expanded=False,
            )

            log_message(
                "[final] workflow completed"
            )
# ==========================================================
# LAST RESULT
# ==========================================================

result = st.session_state.get(
    "last_result"
)

if not result:

    st.info(
        "Enter a topic and generate a blog."
    )
# ==========================================================
# OUTLINE TAB
# ==========================================================

if result:

    with tab_outline:

        st.subheader(
            "Generated Outline"
        )

        outline = result.get(
            "blog_outline"
        )

        if not outline:

            st.info(
                "No outline available."
            )

        else:

            if hasattr(
                outline,
                "model_dump"
            ):

                outline_data = (
                    outline.model_dump()
                )

            elif isinstance(
                outline,
                dict,
            ):

                outline_data = (
                    outline
                )

            else:

                outline_data = json.loads(
                    json.dumps(
                        outline,
                        default=str,
                    )
                )

            st.write(
                "**Title:**",
                outline_data.get(
                    "title"
                ),
            )

            col1, col2, col3 = (
                st.columns(3)
            )

            col1.write(
                "**Audience:** "
                + str(
                    outline_data.get(
                        "audience"
                    )
                )
            )

            col2.write(
                "**Tone:** "
                + str(
                    outline_data.get(
                        "tone"
                    )
                )
            )

            col3.write(
                "**Category:** "
                + str(
                    outline_data.get(
                        "category"
                    )
                )
            )

            restrictions = (
                outline_data.get(
                    "restrictions",
                    [],
                )
            )

            if restrictions:

                st.markdown(
                    "### Restrictions"
                )

                for item in restrictions:

                    st.markdown(
                        f"- {item}"
                    )

            sections = (
                outline_data.get(
                    "sections",
                    [],
                )
            )

            if sections:

                section_table = (
                    pd.DataFrame(
                        [
                            {
                                "ID":
                                    section.get(
                                        "section_id"
                                    ),

                                "Heading":
                                    section.get(
                                        "heading"
                                    ),

                                "Target Length":
                                    section.get(
                                        "target_length"
                                    ),

                                "Research":
                                    section.get(
                                        "research_required"
                                    ),

                                "Citations":
                                    section.get(
                                        "citations_required"
                                    ),

                                "Code":
                                    section.get(
                                        "code_required"
                                    ),

                                "Labels":
                                    ", ".join(
                                        section.get(
                                            "labels",
                                            [],
                                        )
                                    ),
                            }
                            for section
                            in sections
                        ]
                    )
                )

                st.dataframe(
                    section_table,
                    use_container_width=True,
                    hide_index=True,
                )

                with st.expander(
                    "View Full Outline JSON"
                ):

                    st.json(
                        outline_data
                    )
# ==========================================================
# SOURCES TAB
# ==========================================================

    with tab_sources:

        st.subheader(
            "Research Sources"
        )

        sources = result.get(
            "collected_sources"
        ) or []

        if not sources:

            st.info(
                "No sources returned. "
                "Topic may have used closed-book mode."
            )

        else:

            rows = []

            for source in sources:

                if hasattr(
                    source,
                    "model_dump"
                ):

                    source = (
                        source.model_dump()
                    )

                rows.append(
                    {
                        "Title":
                            source.get(
                                "title"
                            ),

                        "Published":
                            source.get(
                                "published_date"
                            ),

                        "Source":
                            source.get(
                                "source_name"
                            ),

                        "URL":
                            source.get(
                                "url"
                            ),
                    }
                )

            source_df = (
                pd.DataFrame(
                    rows
                )
            )

            st.dataframe(
                source_df,
                use_container_width=True,
                hide_index=True,
            )

            with st.expander(
                "View Raw Sources"
            ):

                st.json(
                    rows
                )
# ==========================================================
# PREVIEW TAB
# ==========================================================

    with tab_preview:

        st.subheader(
            "Blog Preview"
        )

        markdown_text = (
            result.get(
                "final_markdown"
            )
            or ""
        )

        if not markdown_text:

            st.warning(
                "No markdown generated."
            )

        else:

            render_markdown_content(
                markdown_text
            )

            outline = result.get(
                "blog_outline"
            )

            blog_title = "blog"

            if hasattr(
                outline,
                "title"
            ):

                blog_title = (
                    outline.title
                )

            elif isinstance(
                outline,
                dict,
            ):

                blog_title = (
                    outline.get(
                        "title",
                        "blog",
                    )
                )

            else:

                blog_title = (
                    extract_blog_title(
                        markdown_text,
                        "blog",
                    )
                )

            markdown_filename = (
                f"{slugify(blog_title)}.md"
            )

            st.download_button(
                "⬇️ Download Markdown",
                data=markdown_text.encode(
                    "utf-8"
                ),
                file_name=
                    markdown_filename,
                mime=
                    "text/markdown",
            )

            bundle = (
                create_bundle_zip(
                    markdown_text,
                    markdown_filename,
                    Path(
                        "generated_diagrams"
                    ),
                )
            )

            st.download_button(
                "📦 Download Blog Bundle",
                data=bundle,
                file_name=
                    f"{slugify(blog_title)}_bundle.zip",
                mime=
                    "application/zip",
            )
# ==========================================================
# DIAGRAMS TAB
# ==========================================================

    with tab_diagrams:

        st.subheader(
            "Generated Diagrams"
        )

        diagrams = (
            result.get(
                "planned_diagrams"
            )
            or []
        )

        diagram_folder = Path(
            "generated_diagrams"
        )

        if (
            not diagrams
            and
            not diagram_folder.exists()
        ):

            st.info(
                "No diagrams generated."
            )

        else:

            if diagrams:

                st.markdown(
                    "### Diagram Plan"
                )

                st.json(
                    diagrams
                )

            if (
                diagram_folder.exists()
            ):

                files = [
                    file
                    for file
                    in diagram_folder.iterdir()
                    if file.is_file()
                ]

                if not files:

                    st.warning(
                        "Diagram folder exists but is empty."
                    )

                else:

                    for image_file in sorted(
                        files
                    ):

                        st.image(
                            str(
                                image_file
                            ),
                            caption=
                                image_file.name,
                            use_container_width=
                                True,
                        )

                archive = (
                    create_diagram_zip(
                        diagram_folder
                    )
                )

                if archive:

                    st.download_button(
                        "⬇️ Download Diagrams",
                        data=archive,
                        file_name=
                            "generated_diagrams.zip",
                        mime=
                            "application/zip",
                    )
# ==========================================================
# LOGS TAB
# ==========================================================

    with tab_logs:

        st.subheader(
            "Execution Logs"
        )

        if runtime_logs:

            st.session_state[
                "logs"
            ].extend(
                runtime_logs
            )

        st.text_area(
            "Logs",
            value=
                "\n\n".join(
                    st.session_state[
                        "logs"
                    ][-100:]
                ),
            height=550,
        )