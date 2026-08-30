import { useEffect, useMemo, useState } from "react";
import MarkdownPreview from "./MarkdownPreview";
import {
  blogToState,
  deleteBlog,
  generateBlog,
  getBlog,
  listBlogs,
} from "./api";
import { downloadText, slugify } from "./storage";

const TABS = [
  { id: "outline", label: "Outline" },
  { id: "sources", label: "Sources" },
  { id: "preview", label: "Preview" },
  { id: "diagrams", label: "Diagrams" },
  { id: "logs", label: "Logs" },
];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function sectionCount(state) {
  const sections = state?.generated_sections;
  return Array.isArray(sections) ? sections.length : 0;
}

export default function App() {
  const [topic, setTopic] = useState("");
  const [currentDate, setCurrentDate] = useState(todayIso());
  const [running, setRunning] = useState(false);
  const [activeNode, setActiveNode] = useState(null);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [logs, setLogs] = useState([]);
  const [tab, setTab] = useState("preview");
  const [saved, setSaved] = useState([]);
  const [selectedSaved, setSelectedSaved] = useState("");

  useEffect(() => {
    listBlogs()
      .then(setSaved)
      .catch(() => {
        setSaved([]);
      });
  }, []);

  const outline = result?.blog_outline ?? null;
  const sources = result?.collected_sources ?? [];
  const assets = result?.diagram_assets ?? [];
  const markdown = result?.final_markdown || "";

  const progress = useMemo(
    () => ({
      strategy: result?.routing_strategy || "—",
      research: result?.research_needed ? "yes" : "no",
      queries: (result?.search_queries ?? []).slice(0, 5),
      sources: sources.length,
      sections: sectionCount(result),
      diagrams: assets.length,
    }),
    [result, sources.length, assets.length],
  );

  async function onGenerate(event) {
    event.preventDefault();

    if (!topic.trim() || running) {
      return;
    }

    setRunning(true);
    setError(null);
    setResult({});
    setActiveNode("routing_agent");
    setTab("logs");
    setLogs((current) => [
      ...current,
      `[start] ${new Date().toISOString()} · ${topic.trim()}`,
    ]);

    try {
      await generateBlog(topic.trim(), currentDate, (event) => {
        if (event.type === "progress") {
          setActiveNode(event.node);
          setResult(event.state);
          setLogs((current) => [
            ...current,
            `[${event.node ?? "update"}] sources=${event.state.collected_sources?.length ?? 0} sections=${sectionCount(event.state)}`,
          ]);
        } else if (event.type === "done") {
          setResult(event.state);

          if (event.persist_error) {
            setError(`Generated, but MongoDB save failed: ${event.persist_error}`);
          }

          listBlogs()
            .then((blogs) => {
              setSaved(blogs);
              if (event.blog?.id) {
                setSelectedSaved(event.blog.id);
              }
            })
            .catch(() => undefined);

          setTab("preview");
          setLogs((current) => [...current, "[done] workflow completed"]);
        } else if (event.type === "error") {
          setError(event.message);
          setLogs((current) => [...current, `[error] ${event.message}`]);
        }
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setLogs((current) => [...current, `[error] ${message}`]);
    } finally {
      setRunning(false);
      setActiveNode(null);
    }
  }

  async function loadSaved() {
    if (!selectedSaved) {
      return;
    }

    try {
      const blog = await getBlog(selectedSaved);
      setResult(blogToState(blog));
      setTopic(blog.topic || blog.title);
      setTab("preview");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    }
  }

  async function removeSaved() {
    if (!selectedSaved) {
      return;
    }

    try {
      await deleteBlog(selectedSaved);
      const blogs = await listBlogs();
      setSaved(blogs);
      setSelectedSaved("");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    }
  }

  const downloadName = slugify(outline?.title || topic || "blog");

  return (
    <div className="shell">
      <aside className="rail">
        <p className="eyebrow">Gemini · LangGraph</p>
        <h1>Blog Writing Agent</h1>
        <p className="lede">
          Route, research, draft, and illustrate a technical post. Diagrams go
          to Cloudinary; posts are saved in MongoDB.
        </p>

        <form className="compose" onSubmit={onGenerate}>
          <label htmlFor="topic">Topic</label>
          <textarea
            id="topic"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder="e.g. How RAG evaluation actually fails in production"
            rows={7}
          />

          <label htmlFor="date">Current date</label>
          <input
            id="date"
            type="date"
            value={currentDate}
            onChange={(event) => setCurrentDate(event.target.value)}
          />

          <button type="submit" disabled={running || !topic.trim()}>
            {running ? "Generating…" : "Generate"}
          </button>
        </form>

        {running && (
          <div className="pulse">
            <span className="dot" />
            {activeNode ?? "working"}
          </div>
        )}

        <div className="saved">
          <h2>Saved in MongoDB</h2>
          {saved.length === 0 ? (
            <p className="muted">Generated posts are stored with Cloudinary image URLs.</p>
          ) : (
            <>
              <select
                value={selectedSaved}
                onChange={(event) => setSelectedSaved(event.target.value)}
              >
                <option value="">Select a post</option>
                {saved.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
              <button type="button" className="ghost" onClick={loadSaved}>
                Load
              </button>
              <button type="button" className="ghost" onClick={removeSaved}>
                Delete
              </button>
            </>
          )}
        </div>
      </aside>

      <main className="stage">
        <header className="status">
          <dl>
            <div>
              <dt>Strategy</dt>
              <dd>{progress.strategy}</dd>
            </div>
            <div>
              <dt>Research</dt>
              <dd>{progress.research}</dd>
            </div>
            <div>
              <dt>Sources</dt>
              <dd>{progress.sources}</dd>
            </div>
            <div>
              <dt>Sections</dt>
              <dd>{progress.sections}</dd>
            </div>
            <div>
              <dt>Diagrams</dt>
              <dd>{progress.diagrams}</dd>
            </div>
          </dl>
        </header>

        {error && <div className="banner">{error}</div>}

        <nav className="tabs">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={tab === item.id ? "active" : ""}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <section className="panel">
          {tab === "outline" && (
            <>
              {!outline ? (
                <p className="muted">No outline yet. Generate a post first.</p>
              ) : (
                <>
                  <h2>{outline.title}</h2>
                  <p className="meta">
                    {outline.audience} · {outline.tone} · {outline.category}
                  </p>
                  {outline.restrictions?.length > 0 && (
                    <ul>
                      {outline.restrictions.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  )}
                  <table>
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Heading</th>
                        <th>Length</th>
                        <th>Research</th>
                        <th>Citations</th>
                        <th>Code</th>
                      </tr>
                    </thead>
                    <tbody>
                      {outline.sections.map((section) => (
                        <tr key={section.section_id}>
                          <td>{section.section_id}</td>
                          <td>{section.heading}</td>
                          <td>{section.target_length}</td>
                          <td>{section.research_required ? "yes" : "—"}</td>
                          <td>{section.citations_required ? "yes" : "—"}</td>
                          <td>{section.code_required ? "yes" : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
            </>
          )}

          {tab === "sources" && (
            <>
              {sources.length === 0 ? (
                <p className="muted">
                  No sources. Closed-book topics skip web research.
                </p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Published</th>
                      <th>Source</th>
                      <th>URL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((source) => (
                      <tr key={source.url}>
                        <td>{source.title}</td>
                        <td>{source.published_date || "—"}</td>
                        <td>{source.source_name || "—"}</td>
                        <td>
                          <a href={source.url} target="_blank" rel="noreferrer">
                            {source.url}
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {progress.queries.length > 0 && (
                <>
                  <h3>Search queries</h3>
                  <ul>
                    {progress.queries.map((query) => (
                      <li key={query}>{query}</li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}

          {tab === "preview" && (
            <>
              {!markdown ? (
                <p className="muted">Enter a topic and generate a blog.</p>
              ) : (
                <>
                  <div className="actions">
                    <button
                      type="button"
                      className="ghost"
                      onClick={() =>
                        downloadText(
                          `${downloadName}.md`,
                          markdown,
                          "text/markdown",
                        )
                      }
                    >
                      Download markdown
                    </button>
                  </div>
                  <MarkdownPreview markdown={markdown} />
                </>
              )}
            </>
          )}

          {tab === "diagrams" && (
            <>
              {assets.length === 0 ? (
                <p className="muted">
                  No Cloudinary diagrams for this run.
                </p>
              ) : (
                <div className="gallery">
                  {assets.map((asset) => (
                    <figure key={asset.cloudinary_public_id || asset.url}>
                      <img src={asset.url} alt={asset.alt_text} />
                      <figcaption>
                        {asset.caption}
                        <a href={asset.url} target="_blank" rel="noreferrer">
                          Open on Cloudinary
                        </a>
                      </figcaption>
                    </figure>
                  ))}
                </div>
              )}
            </>
          )}

          {tab === "logs" && (
            <pre className="log">{logs.slice(-120).join("\n")}</pre>
          )}
        </section>
      </main>
    </div>
  );
}
