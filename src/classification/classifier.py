"""
Classification stage.

Extractors already attach a coarse category hint (from discovery/seeds.py)
based on which query surfaced the record. This stage:

  1. Maps entity_type -> its base category (e.g. every Model gets "Models")
     so category coverage is guaranteed even if the hint was missed.
  2. Applies keyword-based secondary classification (e.g. a Tool whose
     description mentions "chat" or "assistant" also gets "Personal";
     one mentioning "image"/"video"/"generate" also gets "Creative").
  3. Flags "New/Recently added" based on the `is_recent` bookkeeping field
     set during normalization.

This is intentionally rule-based (not ML) for determinism and auditability
— appropriate for a pipeline that must be reproducible and explainable.
"""

from __future__ import annotations

import re

from src.schemas.entity import Entity, EntityType
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

_BASE_CATEGORY = {
    EntityType.TOOL: "Tools",
    EntityType.TASK: "Tasks",
    EntityType.COMPANY: "Companies",
    EntityType.NEWS: "News",
    EntityType.VIDEO: "Videos",
    EntityType.ROBOT: "Robots",
    EntityType.DEVICE: "Devices",
    EntityType.MODEL: "Models",
    EntityType.REPOSITORY: "Repositories",
    EntityType.MCP: "MCP",
    EntityType.COLLECTION: "Collections",
    EntityType.PERSONAL: "Personal",
    EntityType.CREATIVE: "Creative",
}

_CREATIVE_KEYWORDS = {"image", "video", "generate", "diffusion", "art", "music", "voice", "creative", "design"}
_PERSONAL_KEYWORDS = {"assistant", "chat", "personal", "companion", "productivity"}
_ROBOT_KEYWORDS = {"robot", "humanoid", "manipulator", "actuator"}
_DEVICE_KEYWORDS = {"edge", "hardware", "chip", "wearable", "device", "embedded"}


def _keyword_hits(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(kw)}\b", lowered) for kw in keywords)


def classify_entity(entity: Entity) -> Entity:
    categories = set(entity.categories)
    categories.add(_BASE_CATEGORY.get(entity.entity_type, entity.entity_type.value))

    haystack = f"{entity.name} {entity.description}"
    if _keyword_hits(haystack, _CREATIVE_KEYWORDS):
        categories.add("Creative")
    if _keyword_hits(haystack, _PERSONAL_KEYWORDS):
        categories.add("Personal")
    if _keyword_hits(haystack, _ROBOT_KEYWORDS) and entity.entity_type in (EntityType.TOOL, EntityType.REPOSITORY):
        categories.add("Robots")
    if _keyword_hits(haystack, _DEVICE_KEYWORDS) and entity.entity_type in (EntityType.TOOL, EntityType.REPOSITORY):
        categories.add("Devices")

    if entity.is_recent:
        categories.add("New/Recently added")

    return entity.model_copy(update={"categories": sorted(categories)})


def classify_all(entities: list[Entity]) -> list[Entity]:
    classified = [classify_entity(e) for e in entities]
    logger.info("Classification complete for %d entities", len(classified))
    return classified
