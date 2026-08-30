from __future__ import annotations

import os
from typing import Optional

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

_client: Optional[MongoClient] = None


def mongodb_uri() -> str:
    uri = os.getenv("MONGODB_URI", "").strip()

    if not uri:
        raise RuntimeError("MONGODB_URI is not set.")

    return uri


def mongodb_db_name() -> str:
    return os.getenv("MONGODB_DB_NAME", "blog_writing_agent")


def get_client() -> MongoClient:
    global _client

    if _client is None:
        _client = MongoClient(mongodb_uri())

    return _client


def get_db() -> Database:
    return get_client()[mongodb_db_name()]


def blogs_collection() -> Collection:
    return get_db()["blogs"]


def ensure_indexes() -> None:
    collection = blogs_collection()
    collection.create_index("created_at")
    collection.create_index("slug")


def connect_mongo() -> None:
    get_client()
    ensure_indexes()


def ping_mongo() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False


def close_client() -> None:
    global _client

    if _client is not None:
        _client.close()
        _client = None
