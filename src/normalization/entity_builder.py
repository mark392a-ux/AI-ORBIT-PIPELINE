"""
Builds validated `Entity` objects from the loosely-typed "pre-entity" dicts
that each extractor produces. This is the single choke point where:

  1. Text is sanitized (src.cleaning.text_sanitizer)
  2. URLs are normalized (src.normalization.url_normalizer)
  3. Deterministic IDs are generated (Entity.generate_id)
  4. Specialized metadata sub-objects are attached based on entity_type

Any record that fails validation here is dropped with a logged reason
rather than silently corrupting the dataset — this is the "resilience +
logging for missing fields" requirement in practice.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from src.cleaning.text_sanitizer import sanitize_description
from src.normalization.url_normalizer import normalize_url
from src.schemas.entity import (
    Entity,
    EntityType,
    SourceInfo,
    ModelMetadata,
    RepositoryMetadata,
    MCPMetadata,
    CompanyMetadata,
    VideoMetadata,
    NewsMetadata,
)
from src.utils.config import CONFIG
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def _is_recent(date_str: str | None) -> bool:
    if not date_str:
        return False
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=CONFIG.recent_days_threshold)
        return dt >= cutoff
    except (ValueError, TypeError):
        return False


def _build_specialized_metadata(entity_type: str, pre: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    if entity_type == "Model":
        kwargs["model_metadata"] = ModelMetadata(
            license=pre.get("license"),
            modalities=pre.get("modalities", []) or [],
            provider=pre.get("provider"),
            downloads=pre.get("downloads"),
            likes=pre.get("likes"),
            library=pre.get("library"),
        )
    elif entity_type in ("Repository", "MCP"):
        kwargs["repository_metadata"] = RepositoryMetadata(
            stars=pre.get("stars"),
            forks=pre.get("forks"),
            primary_language=pre.get("primary_language"),
            last_updated=pre.get("last_updated"),
            open_issues=pre.get("open_issues"),
            license=pre.get("license"),
            topics=pre.get("topics", []) or [],
        )
        if entity_type == "MCP":
            kwargs["mcp_metadata"] = MCPMetadata(
                installation_methods=pre.get("installation_methods", []) or _infer_install_methods(pre),
                runtime_requirements=pre.get("runtime_requirements", []) or _infer_runtime(pre),
                transport=pre.get("transport"),
            )
    elif entity_type == "Company":
        kwargs["company_metadata"] = CompanyMetadata(
            founding_year=pre.get("founding_year"),
            industry_sector=pre.get("industry_sector", "Artificial Intelligence"),
            headquarters=pre.get("headquarters"),
            employee_range=pre.get("employee_range"),
        )
    elif entity_type == "Video":
        kwargs["video_metadata"] = VideoMetadata(
            channel=pre.get("channel"),
            published_at=pre.get("published_at"),
            duration_seconds=pre.get("duration_seconds"),
            view_count=pre.get("view_count"),
        )
    elif entity_type == "News":
        kwargs["news_metadata"] = NewsMetadata(
            published_at=pre.get("published_at"),
            publisher=pre.get("publisher"),
        )

    return kwargs


def _infer_install_methods(pre: dict[str, Any]) -> list[str]:
    """Best-effort inference from repo metadata when not explicitly known."""
    lang = (pre.get("primary_language") or "").lower()
    methods = []
    if lang == "python":
        methods.append("pip install")
    if lang in ("javascript", "typescript"):
        methods.append("npm install")
    if lang == "go":
        methods.append("go install")
    methods.append("Clone from source")
    return methods


def _infer_runtime(pre: dict[str, Any]) -> list[str]:
    lang = pre.get("primary_language")
    return [lang] if lang else []


def build_entity(pre: dict[str, Any]) -> Entity | None:
    """
    Attempts to build a validated Entity from a raw pre-entity dict.
    Returns None (and logs) if the record is unusable — e.g. missing a
    name or URL, which we treat as a hard requirement for traceability.
    """
    try:
        entity_type = pre["entity_type"]
        name = (pre.get("name") or "").strip()
        url = normalize_url(pre.get("url") or pre.get("source_url") or "")

        if not name or not url:
            logger.warning("Dropping record with missing name/url: %r", pre.get("name") or pre)
            return None

        description = sanitize_description(pre.get("description_raw", ""))
        entity_id = Entity.generate_id(entity_type, url)

        specialized = _build_specialized_metadata(entity_type, pre)

        entity = Entity(
            id=entity_id,
            entity_type=EntityType(entity_type),
            name=name,
            description=description,
            url=url,
            categories=list(dict.fromkeys(pre.get("categories", []))),  # dedup preserve order
            source=SourceInfo(name=pre.get("source_name", "Unknown"), url=normalize_url(pre.get("source_url", url))),
            is_recent=_is_recent(pre.get("last_updated") or pre.get("published_at")),
            **specialized,
        )
        return entity

    except (ValidationError, KeyError, ValueError) as exc:
        logger.error("Failed to build entity from %r: %s", pre.get("name", "<unknown>"), exc)
        return None
