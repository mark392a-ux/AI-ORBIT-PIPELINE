"""
RSS/news extractor — parses official publisher RSS feeds via `feedparser`.
This is API-first in spirit: RSS is the publisher's own structured feed
format, not HTML scraping of article pages.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import feedparser

from src.discovery.seeds import RSS_FEEDS
from src.utils.config import CONFIG
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

CACHE_PATH = Path(CONFIG.raw_dir) / "rss_cache.json"


def _load_cache() -> list[dict[str, Any]]:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded %d cached RSS records from %s", len(data), CACHE_PATH)
        return data
    return []


def extract_rss_news(max_per_feed: int = 15) -> list[dict[str, Any]]:
    raw_records: list[dict[str, Any]] = []

    for feed_spec in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_spec["url"])
            if parsed.bozo and not parsed.entries:
                raise ValueError(f"Feed parse error: {parsed.bozo_exception}")
            entries = parsed.entries[:max_per_feed]
            logger.info("RSS feed %r returned %d entries", feed_spec["name"], len(entries))
            for entry in entries:
                raw_records.append(
                    {
                        "title": entry.get("title", ""),
                        "summary": entry.get("summary", entry.get("description", "")),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", entry.get("updated", "")),
                        "_source_name": feed_spec["name"],
                    }
                )
        except Exception as exc:  # noqa: BLE001 — any feed can fail idiosyncratically
            logger.error("RSS feed %r failed: %s", feed_spec["name"], exc)
            continue

    if not raw_records:
        logger.warning("Live RSS extraction returned nothing — falling back to cache.")
        raw_records = _load_cache()

    logger.info("RSS extraction complete: %d raw records", len(raw_records))
    return raw_records


def raw_news_to_entity_dict(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_type": "News",
        "name": raw.get("title", "Untitled"),
        "description_raw": raw.get("summary", ""),
        "url": raw.get("link", ""),
        "categories": ["News"],
        "source_name": raw.get("_source_name", "RSS"),
        "source_url": raw.get("link", ""),
        "published_at": raw.get("published"),
        "publisher": raw.get("_source_name"),
    }
