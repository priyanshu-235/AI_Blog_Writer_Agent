# Blog Writing Agent

A multi-agent technical blog generator. Given a topic, the system decides whether web research is required, plans a structured outline, writes sections in parallel, optionally generates diagrams, uploads those images to Cloudinary, and persists the finished post in MongoDB so it can be loaded and rendered later.

**In-depth internals** (flows, functions, scale, cost, interview Qs): see **[docs/](docs/README.md)**.

The control plane is a **LangGraph** `StateGraph`. Text and images are produced with **Google Gemini**. Research uses **Tavily**. The HTTP API is **FastAPI**. The UI is a **React (Vite + JSX)** app.

The control plane is a **LangGraph** `StateGraph`. Text and images are produced with **Google Gemini**. Research uses **Tavily**. The HTTP API is **FastAPI**. The UI is a **React (Vite + JSX)** app.

Typical deployment split:

| Piece | Runtime | Host |
|---|---|---|
| API + agent graph | Python 3.12, Uvicorn | Render |
| UI | Static Vite build | Vercel |
| Images | Cloudinary `secure_url` | Cloudinary |
| Posts | `blogs` collection | MongoDB Atlas (or any Mongo server) |

Generation is long-running (often several minutes). The API streams NDJSON node updates so the UI can show progress without waiting for a single blocking JSON response.

---

## Capabilities

- **Adaptive research routing.** A dedicated router classifies the topic as `closed_book`, `hybrid`, or `open_book` and either skips the web or issues targeted Tavily queries.
- **Structured planning.** The planner emits a Pydantic `BlogBlueprint` (title, audience, tone, category, 5–9 sections with objectives and key points).
- **Fan-out section writing.** Each section is dispatched with LangGraph `Send` so writers can run as parallel graph tasks. Drafts are merged by `section_id`.
- **Diagram subgraph.** A nested graph plans at most three explanatory diagrams, generates image bytes with Gemini, uploads to Cloudinary, and splices `![alt](https://...)` into markdown.
- **Streaming generate.** `POST /api/generate` yields one JSON object per graph update, then a terminal `done` event that includes the saved Mongo document when persistence succeeds.
- **Durable posts.** Markdown, outline, sources, search queries, and diagram metadata (`secure_url`, `cloudinary_public_id`) live in MongoDB. Delete removes the document and destroys the Cloudinary assets.

---

## Architecture

```
┌─────────────┐     NDJSON stream      ┌──────────────────┐
│  React UI   │ ─────────────────────► │  FastAPI (api.py) │
│  Vite/JSX   │ ◄─────────────────────   │  CORS + routers   │
└─────────────┘     progress / done     └─────────┬──────────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    │                            ▼                            │
                    │                 LangGraph blog_writer_app             │
                    │  routing → (research → freshness filter) → planner     │
                    │       → fan-out section_writer → combine → diagrams       │
                    └─────────────┬──────────────────────────┬───────────────────┘
                                  │                      │
                                  ▼                      ▼
                           Gemini text            Gemini image
                           (ChatGoogle            (google.genai
                            GenerativeAI)          IMAGE modality)
                                  │                      │
                                  │                      ▼
                                  │                 Cloudinary
                                  │                 folder:
                                  │                 blog-writing-agent/<slug>/
                                  ▼
                             MongoDB `blogs`
```

The frontend never talks to Gemini, Tavily, Cloudinary, or MongoDB. Those credentials stay on the API process.

### Process boundaries

- **Render** holds `GOOGLE_API_KEY`, Tavily, Cloudinary, `MONGODB_URI`, and `CORS_ORIGINS`.
- **Vercel** only needs `VITE_API_URL` (the Render origin, no trailing slash). That value is baked in at **build** time (`import.meta.env.VITE_API_URL`).
- Local Vite proxies `/api` and `/health` to `http://127.0.0.1:8000` so you can omit `VITE_API_URL` during development.

---

## Agent graph

Compiled in `backend/graph.py`. Shared state is `BlogWorkflowState` (`backend/state.py`), a `TypedDict`. Section drafts use `Annotated[list[tuple[int, str]], operator.add]` so parallel writers concatenate instead of overwriting.

```
START
  └─ routing_agent
        ├─ (research_needed) research_agent → filter_recent_sources ─┐
        └─ (else) ──────────────────────────────────────────────────┤
                                                                   ▼
                                                            planning_agent
                                                                   │
                                              Send("section_writer") × N sections
                                                                   ▼
                                                            combine_sections
                                                                   ▼
                                                            diagram_pipeline
                                                              ├─ diagram_planner
                                                              ├─ render_diagrams
                                                              └─ finalize_blog
                                                                   ▼
                                                                  END
```

### Routing (`backend/agents/routing.py`)

The router LLM returns a `RoutingDecision`:

| Strategy | Meaning | Freshness window | Research |
|---|---|---|---|
| `closed_book` | Evergreen / stable technical knowledge | ~3650 days (unused for filtering) | No Tavily |
| `hybrid` | Mostly evergreen, needs recent tools/examples | 45 days | Yes |
| `open_book` | News, pricing, launches, roundups | 7 days | Yes; planner category forced to `news_roundup` |

If `TAVILY_API_KEY` is missing, lookup returns `[]` and the run continues as closed-book content with an empty source list.

### Research (`backend/agents/research.py`, `backend/services/tavily.py`)

1. Up to 10 search queries from the router.
2. Each query is executed with the official **Tavily Python client** (`TavilyClient.search`), not the deprecated `langchain_community` `TavilySearchResults` wrapper.
3. A second LLM pass curates hits into `ResearchBundle` (dedupe by URL, drop weak rows).
4. `filter_recent_sources` applies the date cutoff **only** for `open_book`. Sources without a parseable ISO date are dropped in that mode.

### Planning and writing

- Planner: `BlogBlueprint` with 5–9 `SectionBlueprint` rows (`objective`, 3–6 `key_points`, `target_length`, `research_required` / `citations_required` / `code_required`).
- `distribute_sections` emits one `Send` per section with outline + sources serialized via `model_dump()`.
- Writers emit markdown starting with `## Heading`. Open-book instructions forbid inventing facts; missing evidence should be stated as not found in provided sources.
- `combine_sections` sorts by `section_id` and prefixes `# {title}`.

### Diagram subgraph (`backend/agents/diagrams.py`)

- Planner may insert `[[DIAGRAM_1]]` … `[[DIAGRAM_3]]` or return `diagrams=[]`.
- `render_diagrams` calls Gemini image generation (`BLOG_IMAGE_MODEL`, default `gemini-2.5-flash-image`), then Cloudinary upload with `resource_type=image`.
- Cloudinary public IDs are namespaced: `blog-writing-agent/<slug>/<filename-stem>`. Reusing the same Cloudinary **account** as another app is safe as long as that app uses a different folder prefix.
- Failures become a markdown blockquote; the rest of the article still saves.
- Assets on graph state include `url` / `secure_url`, `cloudinary_public_id`, alt text, and caption so Mongo and the UI gallery stay aligned.

---

## HTTP API

Entry: repo-root `api.py` re-exports `app` from `backend/api.py` so Render can run:

```bash
uvicorn api:app --host 0.0.0.0 --port $PORT
```

Lifespan connects Mongo and creates indexes on `created_at` and `slug`. CORS allows `CORS_ORIGINS` (comma-separated) plus `https://*.vercel.app`.

### `GET /health`

```json
{ "ok": true, "mongo": true }
```

`mongo` is a server `ping`. The process still starts if ping later fails; generate persistence will then set `persist_error` on the `done` event.

### `POST /api/generate`

Body:

```json
{
  "topic": "LangGraph multi-agent systems",
  "current_date": "2026-08-30"
}
```

`current_date` is optional (`YYYY-MM-DD`); default is UTC today. Used by the router and freshness filter.

Response: `application/x-ndjson`, one object per line.

| `type` | Fields | When |
|---|---|---|
| `progress` | `node`, `state` | After each graph node update |
| `done` | `state`, `blog?`, `persist_error?` | Graph finished; `blog` is the inserted document |
| `error` | `message` | Uncaught graph/runtime failure |

Headers include `Cache-Control: no-cache` and `X-Accel-Buffering: no` so proxies are less likely to buffer the stream.

The graph is **streamed once**. The API does not `invoke` a second time after streaming.

### Saved blogs

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/api/blogs` | Latest 50 summaries (`id`, title, topic, slug, category, strategy, `diagram_count`, `created_at`) |
| `GET` | `/api/blogs/{id}` | Full document including `markdown` and `diagrams[]` |
| `DELETE` | `/api/blogs/{id}` | `find_one_and_delete`, then `cloudinary.uploader.destroy` per `cloudinary_public_id` |

Invalid ObjectIds return 404.

---

## MongoDB document

Collection: `blogs` (database `MONGODB_DB_NAME`, default `blog_writing_agent`).

```json
{
  "_id": "ObjectId",
  "title": "string",
  "topic": "string",
  "slug": "snake_case_title",
  "routing_strategy": "closed_book | hybrid | open_book",
  "research_needed": true,
  "category": "explainer",
  "audience": "string",
  "tone": "string",
  "markdown": "# Title\n\n...",
  "outline": { "title": "...", "sections": [] },
  "sources": [{ "title": "", "url": "", "snippet": "", "published_date": "", "source_name": "" }],
  "search_queries": ["..."],
  "diagrams": [
    {
      "filename": "architecture.png",
      "secure_url": "https://res.cloudinary.com/...",
      "cloudinary_public_id": "blog-writing-agent/slug/architecture",
      "alt_text": "",
      "caption": "",
      "resource_type": "image"
    }
  ],
  "created_at": "ISODate",
  "updated_at": "ISODate"
}
```

Markdown already contains Cloudinary URLs. The `diagrams` array exists so the UI gallery and deletes do not have to parse markdown.

---

## Frontend

`frontend/` is Vite + React 19, JavaScript only (`.jsx` / `.js`).

- Sidebar: topic, date, generate, Mongo-backed load/delete.
- Main column: strategy/source/section/diagram counters, tabs, scrollable panel. The rail is fixed on desktop; only the article panel scrolls (`frontend/src/index.css`).
- Preview: `react-markdown` + `remark-gfm`. Images load from `https://` Cloudinary URLs.
- Client: `frontend/src/api.js` reads NDJSON from `fetch` (`ReadableStream`). Saved posts are mapped with `blogToState`.

There is no `localStorage` blog cache. Reloading the page lists whatever Mongo returns.

---

## Repository layout

```
.
├── api.py                      # uvicorn target: from backend.api import app
├── Procfile                    # web: uvicorn api:app --host 0.0.0.0 --port $PORT
├── render.yaml                 # Render Blueprint
├── runtime.txt                 # python-3.12.8
├── requirements.txt
├── vercel.json                 # monorepo build → frontend/dist
├── backend/
│   ├── api.py                  # FastAPI app, generate stream, lifespan
│   ├── graph.py                # StateGraph compile
│   ├── schemas.py              # Pydantic contracts
│   ├── state.py                # BlogWorkflowState + initial_workflow_state
│   ├── prompts.py              # System prompts
│   ├── llm.py                  # ChatGoogleGenerativeAI
│   ├── config.py               # BLOG_TEXT_MODEL / BLOG_IMAGE_MODEL
│   ├── utils.py                # slugify, jsonable, merge_graph_update
│   ├── __main__.py             # python -m backend
│   ├── agents/                 # routing, research, planner, writer, diagrams
│   ├── services/               # tavily, gemini_image, cloudinary
│   ├── db/                    # pymongo client, repository
│   └── routers/blogs.py        # CRUD HTTP
└── frontend/
    ├── src/App.jsx
    ├── src/api.js
    ├── vite.config.js          # /api proxy in dev
    └── vercel.json             # SPA rewrite
```

---

## Local development

Requires Python 3.12+, Node 20+, and a filled `.env` at the **repo root** (not inside `backend/`).

```bash
# API — run from repository root
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn api:app --reload --port 8000
```

```bash
# UI
cd frontend
cp .env.example .env   # optional; proxy works without VITE_API_URL
npm install
npm run dev            # http://localhost:5173
```

Health: `http://127.0.0.1:8000/health`.

CLI (no UI, prints markdown; still needs Gemini / optional Tavily / Cloudinary for diagrams):

```bash
python -m backend
```

Do not start Uvicorn from `backend/` as the working directory; `api:app` is the root module.

---

## Environment variables

### API (`.env` / Render)

| Variable | Required | Default | Role |
|---|---|---|---|
| `GOOGLE_API_KEY` | yes | — | Gemini text (`langchain-google-genai`) and image (`google-genai`) |
| `TAVILY_API_KEY` | no | — | Web search; omit to skip research |
| `CLOUDINARY_CLOUD_NAME` | yes for diagrams | — | Cloud name |
| `CLOUDINARY_API_KEY` | yes for diagrams | — | API key |
| `CLOUDINARY_API_SECRET` | yes for diagrams | — | API secret (server-side upload; no unsigned preset) |
| `MONGODB_URI` | yes | — | Atlas or `mongodb://localhost:27017` |
| `MONGODB_DB_NAME` | no | `blog_writing_agent` | Database name |
| `CORS_ORIGINS` | prod | `*` | Comma-separated UI origins, e.g. `https://your-app.vercel.app` |
| `BLOG_TEXT_MODEL` | no | `gemini-2.5-flash` | Text model id |
| `BLOG_IMAGE_MODEL` | no | `gemini-2.5-flash-image` | Image model id |

The same Cloudinary trio can be shared with another project. This app only writes under `blog-writing-agent/`.

### Frontend (Vercel / `frontend/.env`)

| Variable | Role |
|---|---|
| `VITE_API_URL` | Render origin, e.g. `https://blog-writing-agent-api.onrender.com` |

---

## Deployment

### Render (API)

1. New **Web Service** from this repository (or apply `render.yaml`).
2. Build: `pip install -r requirements.txt`. Start: `uvicorn api:app --host 0.0.0.0 --port $PORT`.
3. Health check path: `/health`.
4. Attach all API env vars. After the Vercel URL exists, set `CORS_ORIGINS` to that origin.
5. Atlas **Network Access** must allow Render egress (or `0.0.0.0/0` for a short test).
6. Free instances often kill long generate requests. A paid instance is the realistic default.

### Vercel (UI)

**Recommended:** Project Root Directory = `frontend`. Build `npm run build`, output `dist`. Ignore the repo-root `vercel.json` in that configuration.

**Alternative:** Root of the git repo; root `vercel.json` runs `npm install --prefix frontend` and emits `frontend/dist`.

Then set `VITE_API_URL` and redeploy (env changes require a new build). Preview deployments on `*.vercel.app` are already allowed by the API regex.

---

## Operational notes

- **Timeouts.** Section fan-out plus image generation dominates latency. Keep the HTTP connection open; do not treat a quiet stream as a failure until the process returns `done` or `error`.
- **Idempotency.** Each generate inserts a **new** Mongo document. Cloudinary upload uses `overwrite=True` for the same folder + stem, so regenerating an identical slug can replace an image file while still creating a second blog row.
- **Open-book dates.** Hits without `published_date` / `published_at` never survive the 7-day filter.
- **Secrets.** `.env` is gitignored. Do not commit live keys. Rotate anything that was ever pasted into a tracked file.
- **Models.** Override `BLOG_TEXT_MODEL` / `BLOG_IMAGE_MODEL` if Google retires a default id.

---

## License

Use and modify for your own deployments. Add a `LICENSE` file if you intend a specific open-source grant.
