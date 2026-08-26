"""
YouTube extractor — uses the official YouTube Data API v3 (search.list +
videos.list), never scraping youtube.com HTML.

Requires YOUTUBE_API_KEY. If absent, extraction is skipped with a clear
warning (graceful degradation) rather than failing the whole pipeline —
consistent with "API key optional per-source, pipeline still runs".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from src.discovery.seeds import YOUTUBE_SEARCH_QUERIES
from src.utils.config import CONFIG
from src.utils.logging_config import get_logger
from src.utils.retry import retry_with_backoff

logger = get_logger(__name__)

YT_API_BASE = "https://www.googleapis.com/youtube/v3"
CACHE_PATH = Path(CONFIG.raw_dir) / "youtube_cache.json"


@retry_with_backoff(max_attempts=CONFIG.max_retries, retry_exceptions=(requests.RequestException,))
def _search_videos(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{YT_API_BASE}/search",
        params={
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "order": "relevance",
            "key": CONFIG.youtube_api_key,
        },
        timeout=CONFIG.request_timeout,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def _load_cache() -> list[dict[str, Any]]:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded %d cached YouTube records from %s", len(data), CACHE_PATH)
        return data
    return []


def extract_youtube_videos(max_per_query: int = 8) -> list[dict[str, Any]]:
    if not CONFIG.youtube_api_key:
        logger.warning("YOUTUBE_API_KEY not set — falling back to cached YouTube data if available.")
        return _load_cache()

    raw_records: list[dict[str, Any]] = []
    for query in YOUTUBE_SEARCH_QUERIES:
        try:
            items = _search_videos(query, max_results=max_per_query)
            logger.info("YouTube query %r returned %d videos", query, len(items))
            for item in items:
                item["_query"] = query
            raw_records.extend(items)
        except requests.RequestException as exc:
            logger.error("YouTube query %r failed permanently: %s", query, exc)
            continue

    if not raw_records:
        raw_records = _load_cache()

    logger.info("YouTube extraction complete: %d raw records", len(raw_records))
    return raw_records


def raw_video_to_entity_dict(raw: dict[str, Any]) -> dict[str, Any]:
    snippet = raw.get("snippet", {})
    video_id = raw.get("id", {}).get("videoId") if isinstance(raw.get("id"), dict) else raw.get("id")
    url = f"https://www.youtube.com/watch?v={video_id}"

    return {
        "entity_type": "Video",
        "name": snippet.get("title", "Untitled video"),
        "description_raw": snippet.get("description", ""),
        "url": url,
        "categories": ["Videos"],
        "source_name": "YouTube Data API",
        "source_url": url,
        "channel": snippet.get("channelTitle"),
        "published_at": snippet.get("publishedAt"),
    }
