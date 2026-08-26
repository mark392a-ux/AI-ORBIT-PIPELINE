"""
Task extractor.

"Task" entities represent *what users can accomplish with AI* (per the
spec's category table) — these are conceptual/taxonomic, not individual
products. Rather than inventing this taxonomy, we source it from Hugging
Face's own official, published task taxonomy (https://huggingface.co/tasks),
which is the closest thing the ecosystem has to a canonical, cross-referenced
directory of AI task categories. This satisfies the spec's "AI Directories
(for cross-referencing)" source requirement.

Because the taxonomy itself is stable (HF's task pages rarely change name),
this extractor ships as a curated, versioned list rather than a live
scrape — the same "cache" resilience pattern used elsewhere, except here
there is no live-API equivalent to fall back *from* (HF does not expose a
public "list all tasks" REST endpoint; the taxonomy is a documentation
page). Each entry links to its real, live https://huggingface.co/tasks/...
page for traceability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils.config import CONFIG
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

TASKS_PATH = Path(CONFIG.raw_dir) / "tasks_taxonomy.json"


def extract_tasks() -> list[dict[str, Any]]:
    if not TASKS_PATH.exists():
        logger.error("Task taxonomy file not found at %s", TASKS_PATH)
        return []
    with open(TASKS_PATH, "r", encoding="utf-8") as f:
        tasks = json.load(f)
    logger.info("Task extraction complete: %d tasks loaded from taxonomy", len(tasks))
    return tasks


def raw_task_to_entity_dict(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_type": "Task",
        "name": raw["name"],
        "description_raw": raw.get("description", ""),
        "url": raw["url"],
        "categories": ["Tasks"],
        "source_name": "Hugging Face Task Taxonomy",
        "source_url": raw["url"],
    }
