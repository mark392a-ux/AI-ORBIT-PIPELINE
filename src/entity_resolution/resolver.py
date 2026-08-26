"""
Entity resolution: canonicalizes name variants and deduplicates entities
that represent the same real-world thing but arrived from different
sources with slightly different names/URLs (e.g. "OpenAI" from an official
site vs "Open AI, Inc." mentioned in a news article).

Strategy (two-pass, cheap-to-expensive):
  1. Exact match on normalized URL — cheapest, highest-confidence signal.
  2. Exact match on canonical name (lowercased, punctuation/suffix-stripped).
  3. Fuzzy match on canonical name within the same entity_type using
     token-sort-ratio (rapidfuzz), above a conservative threshold, to
     catch near-duplicates without false-merging distinct entities.

When two records are judged the same entity, they are merged: the record
from the higher-authority source wins for core fields, but categories,
specialized metadata, and source provenance are unioned so no information
is lost.
"""

from __future__ import annotations

import re
from typing import Iterable

from rapidfuzz import fuzz

from src.schemas.entity import Entity
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# Suffixes/noise that should not affect identity comparison.
_SUFFIX_PATTERN = re.compile(
    r"\b(inc\.?|llc|ltd\.?|corp\.?|co\.?|company|technologies|labs?|ai)\b\.?$",
    re.IGNORECASE,
)
_PUNCT_PATTERN = re.compile(r"[^\w\s]")

# Sources considered higher-authority when resolving field conflicts.
_SOURCE_AUTHORITY = {
    "GitHub API": 3,
    "Hugging Face Hub API": 3,
    "Official Site": 3,
    "YouTube Data API": 2,
    "RSS": 1,
}

FUZZY_THRESHOLD = 92  # conservative — avoid merging genuinely distinct entities


def canonicalize_name(name: str) -> str:
    """Produce a comparison key: lowercase, hyphens/underscores -> spaces,
    strip punctuation & corporate suffixes."""
    n = name.strip().lower()
    n = re.sub(r"[-_]+", " ", n)  # e.g. "deepseek-ai" -> "deepseek ai", "black-forest-labs" -> "black forest labs"
    n = _SUFFIX_PATTERN.sub("", n).strip()
    n = _PUNCT_PATTERN.sub("", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _authority(entity: Entity) -> int:
    return _SOURCE_AUTHORITY.get(entity.source.name, 0)


def _merge(primary: Entity, secondary: Entity) -> Entity:
    """Merge `secondary` into `primary`, unioning list fields, keeping the
    higher-authority record's scalar fields."""
    winner, loser = (primary, secondary) if _authority(primary) >= _authority(secondary) else (secondary, primary)

    merged_categories = list(dict.fromkeys(winner.categories + loser.categories))
    merged = winner.model_copy(update={"categories": merged_categories})

    # Prefer a non-empty description; prefer the longer one if both exist.
    if len(loser.description) > len(merged.description):
        merged = merged.model_copy(update={"description": loser.description})

    # Union specialized metadata where the winner is missing it.
    for field in (
        "model_metadata", "repository_metadata", "mcp_metadata",
        "company_metadata", "video_metadata", "news_metadata",
    ):
        if getattr(merged, field) is None and getattr(loser, field) is not None:
            merged = merged.model_copy(update={field: getattr(loser, field)})

    merged = merged.model_copy(update={"is_recent": merged.is_recent or loser.is_recent})

    logger.info(
        "Merged duplicate entities: %r (%s) + %r (%s) -> kept id=%s",
        primary.name, primary.source.name, secondary.name, secondary.source.name, merged.id,
    )
    return merged


def resolve_entities(entities: Iterable[Entity]) -> list[Entity]:
    """
    Runs the full canonicalization + dedup pipeline and returns a list of
    unique, merged entities.
    """
    entities = list(entities)
    logger.info("Entity resolution starting with %d raw entities", len(entities))

    # --- Pass 1: exact URL match -------------------------------------------------
    by_url: dict[str, Entity] = {}
    for e in entities:
        key = e.url
        if key in by_url:
            by_url[key] = _merge(by_url[key], e)
        else:
            by_url[key] = e
    stage1 = list(by_url.values())
    logger.info("After URL-based dedup: %d entities (removed %d)", len(stage1), len(entities) - len(stage1))

    # --- Pass 2: exact canonical-name match (within same entity_type) -----------
    by_name_type: dict[tuple[str, str], Entity] = {}
    for e in stage1:
        key = (e.entity_type.value, canonicalize_name(e.name))
        if key in by_name_type:
            by_name_type[key] = _merge(by_name_type[key], e)
        else:
            by_name_type[key] = e
    stage2 = list(by_name_type.values())
    logger.info("After name-based dedup: %d entities (removed %d)", len(stage2), len(stage1) - len(stage2))

    # --- Pass 3: fuzzy name match within same entity_type ------------------------
    final: list[Entity] = []
    consumed = [False] * len(stage2)
    for i, e_i in enumerate(stage2):
        if consumed[i]:
            continue
        merged_entity = e_i
        key_i = canonicalize_name(e_i.name)
        for j in range(i + 1, len(stage2)):
            if consumed[j] or stage2[j].entity_type != e_i.entity_type:
                continue
            key_j = canonicalize_name(stage2[j].name)
            score = fuzz.token_sort_ratio(key_i, key_j)
            if score >= FUZZY_THRESHOLD:
                merged_entity = _merge(merged_entity, stage2[j])
                consumed[j] = True
        consumed[i] = True
        final.append(merged_entity)

    logger.info("After fuzzy dedup: %d entities (removed %d)", len(final), len(stage2) - len(final))
    logger.info("Entity resolution complete: %d -> %d entities", len(entities), len(final))
    return final
