from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.db.connection import close_client, connect_mongo, ping_mongo
from backend.db.repository import insert_blog
from backend.graph import blog_writer_app
from backend.routers.blogs import router as blogs_router
from backend.state import initial_workflow_state
from backend.utils import jsonable, merge_graph_update


@asynccontextmanager
async def lifespan(_app: FastAPI):
    connect_mongo()
    yield
    close_client()


app = FastAPI(
    title="Blog Writing Agent API",
    version="1.0.0",
    lifespan=lifespan,
)


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "*").strip()

    if raw == "*":
        return ["*"]

    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(blogs_router)


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    current_date: Optional[str] = None


@app.get("/health")
def health():
    return {"ok": True, "mongo": ping_mongo()}


@app.post("/api/generate")
def generate(body: GenerateRequest):
    topic = body.topic.strip()

    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required.")

    inputs = initial_workflow_state(
        topic=topic,
        current_date=body.current_date,
    )

    def event_stream():
        accumulated = dict(inputs)

        try:
            for update in blog_writer_app.stream(
                inputs,
                stream_mode="updates",
            ):
                node = None

                if isinstance(update, dict) and update:
                    node = next(iter(update.keys()))

                accumulated = merge_graph_update(accumulated, update)

                payload = {
                    "type": "progress",
                    "node": node,
                    "state": jsonable(accumulated),
                }

                yield json.dumps(payload, default=str) + "\n"

            saved = None
            persist_error = None

            try:
                saved = insert_blog(jsonable(accumulated))
            except Exception as exc:
                persist_error = str(exc)

            done = {
                "type": "done",
                "state": jsonable(accumulated),
                "blog": saved,
            }

            if persist_error:
                done["persist_error"] = persist_error

            yield json.dumps(done, default=str) + "\n"

        except Exception as exc:
            yield json.dumps(
                {
                    "type": "error",
                    "message": str(exc),
                },
                default=str,
            ) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
