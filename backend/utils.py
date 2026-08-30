from __future__ import annotations

import re
from datetime import date
from typing import Optional


def slugify(text: str) -> str:
    value = text.strip().lower()
    value = re.sub(r"[^a-z0-9 _-]+", "", value)
    value = re.sub(r"\s+", "_", value).strip("_")
    return value or "blog"


def jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()

    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]

    if isinstance(value, date):
        return value.isoformat()

    return value


def merge_graph_update(current: dict, update: dict) -> dict:
    if not isinstance(update, dict):
        return current

    for node_payload in update.values():
        if not isinstance(node_payload, dict):
            continue

        for key, item in node_payload.items():
            if key == "generated_sections" and isinstance(item, list):
                current[key] = list(current.get(key) or []) + item
            else:
                current[key] = item

    return current


def safe_parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None

    try:
        return date.fromisoformat(value[:10])
    except Exception:
        return None
