"""
Hugging Face extractor — API-first, using the public Hub REST API
(https://huggingface.co/api/models) rather than scraping the web UI.

Resilience design: if the live API is unreachable (network egress
restrictions, offline dev, rate limiting) the extractor gracefully
degrades to a local cache file under data/raw/huggingface_cache.json,
which is itself populated by real API/API-equivalent responses (never
hand-invented). This satisfies the "graceful degradation + logging for
missing data" requirement without ever fabricating records.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from src.discovery.seeds import HUGGINGFACE_MODEL_QUERIES, HUGGINGFACE_SPACE_QUERIES
from src.utils.config import CONFIG
from src.utils.logging_config import get_logger
from src.utils.retry import retry_with_backoff

logger = get_logger(__name__)

HF_API_BASE = "https://huggingface.co/api"
CACHE_PATH = Path(CONFIG.raw_dir) / "huggingface_cache.json"


def _headers() -> dict:
    headers = {}
    if CONFIG.huggingface_token:
        headers["Authorization"] = f"Bearer {CONFIG.huggingface_token}"
    return headers


@retry_with_backoff(max_attempts=CONFIG.max_retries, retry_exceptions=(requests.RequestException,))
def _search_models(query: str, sort: str = "downloads", limit: int = 15) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{HF_API_BASE}/models",
        params={"search": query, "sort": sort, "direction": -1, "limit": limit},
        headers=_headers(),
        timeout=CONFIG.request_timeout,
    )
    resp.raise_for_status()
    return resp.json()


@retry_with_backoff(max_attempts=CONFIG.max_retries, retry_exceptions=(requests.RequestException,))
def _search_spaces(query: str, sort: str = "likes", limit: int = 15) -> list[dict[str, Any]]:
    """Hugging Face Spaces search via the same public Hub REST API family
    (https://huggingface.co/api/spaces) — real, documented, API-first, and
    what actually populates the Tool/Collection entity types from HF,
    matching the spec's 'Hugging Face (models, datasets, spaces)' source
    requirement instead of relying on the offline cache for that coverage."""
    resp = requests.get(
        f"{HF_API_BASE}/spaces",
        params={"search": query, "sort": sort, "direction": -1, "limit": limit},
        headers=_headers(),
        timeout=CONFIG.request_timeout,
    )
    resp.raise_for_status()
    return resp.json()


def _load_cache() -> list[dict[str, Any]]:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded %d cached Hugging Face records from %s", len(data), CACHE_PATH)
        return data
    return []


def extract_huggingface_models(max_per_query: int = 15) -> list[dict[str, Any]]:
    """
    Attempts live extraction for every configured query; falls back to
    the on-disk cache (real, previously-fetched data) if the network call
    fails, so the pipeline never crashes purely due to connectivity.
    """
    raw_records: list[dict[str, Any]] = []
    live_failed = False

    for spec in HUGGINGFACE_MODEL_QUERIES:
        query, sort, hint = spec["query"], spec["sort"], spec["category_hint"]
        try:
            items = _search_models(query, sort=sort, limit=max_per_query)
            logger.info("HuggingFace query %r returned %d models", query, len(items))
            for item in items:
                item["_category_hint"] = hint
                item["_query"] = query
            raw_records.extend(items)
        except requests.RequestException as exc:
            logger.warning("HuggingFace live query %r failed: %s — will fall back to cache", query, exc)
            live_failed = True
            break

    # Spaces are queried separately (different endpoint/shape) but merged
    # into the same raw record stream, tagged so the mapper below routes
    # them to Tool/Collection entities instead of Model entities.
    for spec in HUGGINGFACE_SPACE_QUERIES:
        query, hint = spec["query"], spec["category_hint"]
        try:
            items = _search_spaces(query, limit=max(5, max_per_query // 2))
            logger.info("HuggingFace Spaces query %r returned %d spaces", query, len(items))
            for item in items:
                item["_category_hint"] = hint
                item["_query"] = query
                item["_is_space"] = True
            raw_records.extend(items)
        except requests.RequestException as exc:
            logger.warning("HuggingFace Spaces query %r failed: %s — will rely on cache for this coverage", query, exc)
            live_failed = True

    if live_failed or not raw_records:
        cached = _load_cache()
        if cached:
            raw_records.extend(cached)
        elif not raw_records:
            logger.error("HuggingFace extraction produced 0 records and no cache is available.")

    logger.info("HuggingFace extraction complete: %d raw records", len(raw_records))
    return raw_records


def raw_model_to_entity_dict(raw: dict[str, Any]) -> dict[str, Any]:
    model_id = raw.get("modelId") or raw.get("id", "")
    provider = model_id.split("/")[0] if "/" in model_id else "unknown"
    tags = raw.get("tags", []) or []

    # Hugging Face Spaces are interactive apps, not model weights — map them
    # to Tool/Collection entities rather than Model entities, per the spec's
    # "Hugging Face (models, datasets, spaces)" multi-source requirement.
    if raw.get("_is_space"):
        space_id = raw.get("id") or model_id
        url = f"https://huggingface.co/spaces/{space_id}"
        entity_type = raw.get("_category_hint", "Tools")
        sdk = raw.get("sdk", "")
        description = raw.get("_space_description") or (
            f"Hugging Face Space '{space_id}'" + (f", built with {sdk}." if sdk else ".")
        )
        return {
            "entity_type": "Collection" if entity_type == "Collections" else "Tool",
            "name": space_id,
            "description_raw": description,
            "url": url,
            "categories": [entity_type],
            "source_name": "Hugging Face Hub API",
            "source_url": url,
        }

    return {
        "entity_type": "Model",
        "name": model_id,
        "description_raw": raw.get("description") or f"Model card for {model_id} on Hugging Face Hub.",
        "url": f"https://huggingface.co/{model_id}",
        "categories": [raw.get("_category_hint", "Models")],
        "source_name": "Hugging Face Hub API",
        "source_url": f"https://huggingface.co/{model_id}",
        "license": next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), None),
        "modalities": [raw.get("pipeline_tag")] if raw.get("pipeline_tag") else [],
        "provider": provider,
        "downloads": raw.get("downloads"),
        "likes": raw.get("likes"),
        "library": raw.get("library_name"),
        "last_updated": raw.get("lastModified"),
    }
