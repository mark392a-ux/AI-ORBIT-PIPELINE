"""
Official product/company site extractor.

Deliberately "selective" per the spec: rather than crawling, this reads a
small curated list (src/discovery/seeds.py::OFFICIAL_SITES) and enriches
each with a lightweight metadata fetch (the site's own <title>/<meta
description>), used only to produce Company entities that anchor the
"Company develops X" relationships. This keeps footprint low and avoids
brittle, broad scraping.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.discovery.seeds import OFFICIAL_SITES
from src.utils.config import CONFIG
from src.utils.logging_config import get_logger
from src.utils.retry import retry_with_backoff

logger = get_logger(__name__)

CACHE_PATH = Path(CONFIG.raw_dir) / "sites_cache.json"


def _load_cache() -> dict[str, str]:
    """Cache maps site name -> a previously-fetched real meta description,
    used only when the live fetch is blocked (e.g. restricted network)."""
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@retry_with_backoff(max_attempts=2, retry_exceptions=(requests.RequestException,))
def _fetch_meta_description(url: str) -> str:
    resp = requests.get(url, timeout=CONFIG.request_timeout, headers={"User-Agent": "ai-orbit-pipeline/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    return tag["content"].strip() if tag and tag.get("content") else ""


def extract_official_sites() -> list[dict[str, Any]]:
    cache = _load_cache()
    raw_records = []
    for site in OFFICIAL_SITES:
        description = ""
        try:
            description = _fetch_meta_description(site["url"])
        except requests.RequestException as exc:
            description = cache.get(site["name"], "")
            logger.warning(
                "Could not fetch meta description for %s: %s (%s)",
                site["url"], exc, "using cache" if description else "no cache available, leaving blank",
            )

        raw_records.append(
            {
                "name": site["name"],
                "url": site["url"],
                "description_raw": description,
            }
        )
    logger.info("Official sites extraction complete: %d records", len(raw_records))
    return raw_records


def raw_site_to_entity_dict(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_type": "Company",
        "name": raw["name"],
        "description_raw": raw.get("description_raw") or f"{raw['name']} is an AI company.",
        "url": raw["url"],
        "categories": ["Companies"],
        "source_name": "Official Site",
        "source_url": raw["url"],
    }
