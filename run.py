#!/usr/bin/env python3
"""
AI Orbit Data Ingestion Pipeline — main entry point.

Runs the full stage sequence:
  Discovery -> Extraction -> Cleaning/Normalization -> Entity Resolution
  -> Classification -> Relationship Mapping -> Validation -> Write output

Usage:
    python run.py                     # full run, live APIs where keys/network allow
    python run.py --max-per-query 10  # tune volume per source
    python run.py --sources github huggingface   # limit to specific sources
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from src.classification.classifier import classify_all
from src.entity_resolution.resolver import resolve_entities
from src.extractors.github_extractor import extract_github_repositories, raw_repo_to_entity_dict
from src.extractors.huggingface_extractor import extract_huggingface_models, raw_model_to_entity_dict
from src.extractors.rss_extractor import extract_rss_news, raw_news_to_entity_dict
from src.extractors.sites_extractor import extract_official_sites, raw_site_to_entity_dict
from src.extractors.task_extractor import extract_tasks, raw_task_to_entity_dict
from src.extractors.youtube_extractor import extract_youtube_videos, raw_video_to_entity_dict
from src.normalization.entity_builder import build_entity
from src.relationships.relationship_mapper import map_relationships
from src.schemas.entity import Entity
from src.utils.config import CONFIG
from src.utils.logging_config import get_logger
from src.validation.validator import build_quality_report, validate_entities, validate_relationships

logger = get_logger("run")

ALL_SOURCES = ["github", "huggingface", "youtube", "rss", "sites", "tasks"]


def run_extraction_stage(sources: list[str], max_per_query: int) -> list[dict]:
    """Runs Discovery+Extraction for each requested source, converting raw
    API records into pre-entity dicts. Each source is isolated in its own
    try/except so one failing source degrades gracefully instead of
    aborting the whole run."""
    pre_entities: list[dict] = []

    if "github" in sources:
        try:
            raw = extract_github_repositories(max_per_query=max_per_query)
            pre_entities.extend(raw_repo_to_entity_dict(r) for r in raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("GitHub extraction stage failed entirely: %s", exc)

    if "huggingface" in sources:
        try:
            raw = extract_huggingface_models(max_per_query=max_per_query)
            pre_entities.extend(raw_model_to_entity_dict(r) for r in raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("Hugging Face extraction stage failed entirely: %s", exc)

    if "youtube" in sources:
        try:
            raw = extract_youtube_videos(max_per_query=max_per_query)
            pre_entities.extend(raw_video_to_entity_dict(r) for r in raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("YouTube extraction stage failed entirely: %s", exc)

    if "rss" in sources:
        try:
            raw = extract_rss_news(max_per_feed=max_per_query)
            pre_entities.extend(raw_news_to_entity_dict(r) for r in raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("RSS extraction stage failed entirely: %s", exc)

    if "sites" in sources:
        try:
            raw = extract_official_sites()
            pre_entities.extend(raw_site_to_entity_dict(r) for r in raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("Official sites extraction stage failed entirely: %s", exc)

    if "tasks" in sources:
        try:
            raw = extract_tasks()
            pre_entities.extend(raw_task_to_entity_dict(r) for r in raw)
        except Exception as exc:  # noqa: BLE001
            logger.error("Task extraction stage failed entirely: %s", exc)

    logger.info("Extraction stage complete: %d pre-entity records across %d sources", len(pre_entities), len(sources))
    return pre_entities


def run_pipeline(sources: list[str], max_per_query: int, out_dir: Path) -> dict:
    start = time.time()
    logger.info("=== AI Orbit Ingestion Pipeline starting (sources=%s) ===", sources)

    # Discovery + Extraction
    pre_entities = run_extraction_stage(sources, max_per_query)

    # Cleaning + Normalization (per-record) -> Entity objects
    entities: list[Entity] = []
    for pre in pre_entities:
        entity = build_entity(pre)
        if entity is not None:
            entities.append(entity)
    logger.info("Normalization complete: %d/%d records became valid entities", len(entities), len(pre_entities))

    # Entity Resolution (dedup/canonicalize)
    entities = resolve_entities(entities)

    # Classification
    entities = classify_all(entities)

    # Relationship Mapping
    relationships = map_relationships(entities)

    # Validation
    entities = validate_entities(entities)
    relationships = validate_relationships(relationships, entities)

    # Write output
    out_dir.mkdir(parents=True, exist_ok=True)
    entities_path = out_dir / "entities.json"
    relationships_path = out_dir / "relationships.json"

    with open(entities_path, "w", encoding="utf-8") as f:
        json.dump([e.model_dump() for e in entities], f, indent=2, ensure_ascii=False)

    with open(relationships_path, "w", encoding="utf-8") as f:
        json.dump([r.model_dump() for r in relationships], f, indent=2, ensure_ascii=False)

    report = build_quality_report(entities, relationships)
    report["elapsed_seconds"] = round(time.time() - start, 1)

    with open(out_dir / "quality_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("=== Pipeline complete in %.1fs — %d entities, %d relationships ===",
                report["elapsed_seconds"], len(entities), len(relationships))
    logger.info("Output written to %s and %s", entities_path, relationships_path)

    return report


def main():
    parser = argparse.ArgumentParser(description="AI Orbit Data Ingestion Pipeline")
    parser.add_argument("--sources", nargs="+", choices=ALL_SOURCES, default=ALL_SOURCES,
                         help="Which sources to run (default: all)")
    parser.add_argument("--max-per-query", type=int, default=13,
                         help="Max records to pull per query/feed/topic")
    parser.add_argument("--out-dir", type=str, default=CONFIG.data_dir,
                         help="Output directory for entities.json / relationships.json")
    args = parser.parse_args()

    report = run_pipeline(args.sources, args.max_per_query, Path(args.out_dir))
    print(json.dumps(report, indent=2))

    if report["total_entities"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
