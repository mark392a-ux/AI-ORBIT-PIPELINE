"""
GitHub extractor — API-first (REST Search API), no scraping.

Produces raw dicts (not yet Entity objects — that coercion happens in
normalization) for:
  - Repository entities (general OSS projects)
  - MCP entities (repos tagged with mcp-server / model-context-protocol)

Auth: works unauthenticated (60 req/hr) but honors GITHUB_TOKEN if present
for the much higher 5000 req/hr rate limit, per the ".env.example, use env
vars" requirement.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from src.discovery.seeds import GITHUB_TOPIC_QUERIES
from src.utils.config import CONFIG
from src.utils.logging_config import get_logger
from src.utils.retry import retry_with_backoff

logger = get_logger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if CONFIG.github_token:
        headers["Authorization"] = f"Bearer {CONFIG.github_token}"
    return headers


@retry_with_backoff(max_attempts=CONFIG.max_retries, retry_exceptions=(requests.RequestException,))
def _search_repositories(query: str, per_page: int = 15) -> list[dict[str, Any]]:
    """Single call to GitHub's repository search endpoint."""
    resp = requests.get(
        f"{GITHUB_API_BASE}/search/repositories",
        params={"q": query, "sort": "stars", "order": "desc", "per_page": per_page},
        headers=_headers(),
        timeout=CONFIG.request_timeout,
    )
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        logger.warning("GitHub rate limit hit for query=%r", query)
        raise requests.RequestException("GitHub rate limit exceeded")
    resp.raise_for_status()
    return resp.json().get("items", [])


def extract_github_repositories(max_per_query: int = 15) -> list[dict[str, Any]]:
    """
    Runs every configured topic/query against GitHub Search and returns raw
    repo dicts annotated with a `_category_hint` used later by the
    classification stage.
    """
    raw_records: list[dict[str, Any]] = []
    for spec in GITHUB_TOPIC_QUERIES:
        query, hint = spec["query"], spec["category_hint"]
        try:
            items = _search_repositories(query, per_page=max_per_query)
            logger.info("GitHub query %r returned %d repos", query, len(items))
        except requests.RequestException as exc:
            # Graceful degradation: log and continue with other queries
            # rather than aborting the whole extraction stage.
            logger.error("GitHub query %r failed permanently: %s", query, exc)
            continue

        for item in items:
            item["_category_hint"] = hint
            item["_query"] = query
            raw_records.append(item)

        time.sleep(2.5)  # stay under GitHub search's 10 req/min unauthenticated cap

    logger.info("GitHub extraction complete: %d raw records", len(raw_records))
    return raw_records


def raw_repo_to_entity_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Maps a raw GitHub API repository object into the intermediate
    "pre-entity" dict shape consumed by normalization/cleaning. Decides
    Repository vs MCP entity_type based on the category hint / topics.
    """
    topics = raw.get("topics", []) or []
    is_mcp = raw["_category_hint"] == "MCP" or any(
        "mcp" in t or "model-context-protocol" in t for t in topics
    )

    return {
        "entity_type": "MCP" if is_mcp else "Repository",
        "name": raw.get("full_name") or raw.get("name"),
        "description_raw": raw.get("description") or "",
        "url": raw.get("html_url"),
        "categories": [raw["_category_hint"]],
        "source_name": "GitHub API",
        "source_url": raw.get("html_url"),
        "stars": raw.get("stargazers_count"),
        "forks": raw.get("forks_count"),
        "primary_language": raw.get("language"),
        "last_updated": raw.get("pushed_at"),
        "open_issues": raw.get("open_issues_count"),
        "license": (raw.get("license") or {}).get("spdx_id") if raw.get("license") else None,
        "topics": topics,
        "owner_login": (raw.get("owner") or {}).get("login"),
    }
