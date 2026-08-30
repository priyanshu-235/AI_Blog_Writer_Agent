from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId

from backend.db.connection import blogs_collection
from backend.utils import jsonable, slugify


def _now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_blog(document: dict) -> dict:
    payload = dict(document)
    payload["id"] = str(payload.pop("_id"))
    created_at = payload.get("created_at")
    updated_at = payload.get("updated_at")

    if isinstance(created_at, datetime):
        payload["created_at"] = created_at.isoformat()

    if isinstance(updated_at, datetime):
        payload["updated_at"] = updated_at.isoformat()

    return payload


def blog_document_from_state(state: dict) -> dict:
    outline = jsonable(state.get("blog_outline")) or {}
    sources = jsonable(state.get("collected_sources") or [])
    diagrams = []

    for asset in state.get("diagram_assets") or []:
        diagrams.append(
            {
                "filename": asset.get("filename", ""),
                "secure_url": asset.get("url") or asset.get("secure_url", ""),
                "cloudinary_public_id": asset.get("cloudinary_public_id", ""),
                "alt_text": asset.get("alt_text", ""),
                "caption": asset.get("caption", ""),
                "resource_type": asset.get("resource_type", "image"),
            }
        )

    title = outline.get("title") or state.get("topic") or "Untitled blog"
    now = _now()

    return {
        "title": title,
        "topic": state.get("topic", ""),
        "slug": slugify(title),
        "routing_strategy": state.get("routing_strategy", ""),
        "research_needed": bool(state.get("research_needed")),
        "category": outline.get("category"),
        "audience": outline.get("audience"),
        "tone": outline.get("tone"),
        "markdown": state.get("final_markdown") or "",
        "outline": outline or None,
        "sources": sources,
        "search_queries": state.get("search_queries") or [],
        "diagrams": diagrams,
        "created_at": now,
        "updated_at": now,
    }


def insert_blog(state: dict) -> dict:
    collection = blogs_collection()
    document = blog_document_from_state(state)
    result = collection.insert_one(document)
    document["_id"] = result.inserted_id
    return serialize_blog(document)


def list_blogs(limit: int = 50) -> list[dict]:
    collection = blogs_collection()
    documents = collection.find().sort("created_at", -1).limit(limit)
    summaries = []

    for document in documents:
        summaries.append(
            {
                "id": str(document["_id"]),
                "title": document.get("title"),
                "topic": document.get("topic"),
                "slug": document.get("slug"),
                "category": document.get("category"),
                "routing_strategy": document.get("routing_strategy"),
                "diagram_count": len(document.get("diagrams") or []),
                "created_at": (
                    document["created_at"].isoformat()
                    if isinstance(document.get("created_at"), datetime)
                    else document.get("created_at")
                ),
            }
        )

    return summaries


def get_blog(blog_id: str) -> Optional[dict]:
    collection = blogs_collection()

    try:
        object_id = ObjectId(blog_id)
    except InvalidId:
        return None

    document = collection.find_one({"_id": object_id})

    if not document:
        return None

    return serialize_blog(document)


def delete_blog(blog_id: str) -> Optional[dict]:
    collection = blogs_collection()

    try:
        object_id = ObjectId(blog_id)
    except InvalidId:
        return None

    document = collection.find_one_and_delete({"_id": object_id})

    if not document:
        return None

    return serialize_blog(document)
