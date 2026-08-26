"""
Validation stage — the last gate before entities/relationships are
written to disk. Performs:

  1. Schema validation (already guaranteed by pydantic at construction,
     re-checked here defensively).
  2. Uniqueness validation (no duplicate IDs — would indicate a resolver
     bug).
  3. Referential integrity for relationships (source_id/target_id must
     both exist in the resolved entity set — orphan edges are dropped
     and logged rather than shipped).
  4. Required-field completeness reporting (per entity_type, which
     specialized fields are populated) — surfaced as a summary report
     rather than a hard failure, since not every source provides every
     optional field.
"""

from __future__ import annotations

from collections import Counter

from src.schemas.entity import Entity
from src.schemas.relationship import Relationship
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def validate_entities(entities: list[Entity]) -> list[Entity]:
    seen_ids = set()
    valid: list[Entity] = []
    for e in entities:
        if e.id in seen_ids:
            logger.error("Duplicate entity ID detected and dropped: %s (%s)", e.id, e.name)
            continue
        if not e.name or not e.url:
            logger.error("Entity failed final validation (missing name/url): %r", e)
            continue
        seen_ids.add(e.id)
        valid.append(e)

    logger.info("Entity validation: %d/%d entities passed", len(valid), len(entities))
    return valid


def validate_relationships(relationships: list[Relationship], entities: list[Entity]) -> list[Relationship]:
    valid_ids = {e.id for e in entities}
    valid: list[Relationship] = []
    dropped = 0
    for r in relationships:
        if r.source_id not in valid_ids or r.target_id not in valid_ids:
            dropped += 1
            continue
        valid.append(r)

    if dropped:
        logger.warning("Dropped %d relationships with dangling entity references", dropped)
    logger.info("Relationship validation: %d/%d relationships passed", len(valid), len(relationships))
    return valid


def build_quality_report(entities: list[Entity], relationships: list[Relationship]) -> dict:
    type_counts = Counter(e.entity_type.value for e in entities)
    category_counts = Counter(cat for e in entities for cat in e.categories)
    source_counts = Counter(e.source.name for e in entities)
    predicate_counts = Counter(r.predicate.value for r in relationships)

    missing_description = sum(1 for e in entities if not e.description)

    report = {
        "total_entities": len(entities),
        "total_relationships": len(relationships),
        "entities_by_type": dict(type_counts),
        "entities_by_category": dict(category_counts),
        "entities_by_source": dict(source_counts),
        "relationships_by_predicate": dict(predicate_counts),
        "entities_missing_description": missing_description,
    }
    logger.info("Quality report: %s", report)
    return report
