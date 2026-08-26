"""
Relationship-mapping stage: infers typed, directed edges between resolved
entities.

Because our sources rarely state relationships explicitly in structured
form, this stage uses a combination of:

  1. Structural signals already present in metadata — e.g. a GitHub repo's
     `owner_login` matching a known Company's canonical name directly
     implies Company -DEVELOPS-> Repository/MCP.
  2. Lexical co-occurrence — e.g. a Model's `provider` field matching a
     Company's canonical name implies Company -PROVIDES-> Model.
  3. Text-mention matching — scanning descriptions/titles of News/Video
     entities for other entities' canonical names to infer MENTIONS /
     DEMONSTRATES edges.
  4. Category co-membership heuristics — e.g. any Tool sharing a category
     with a Task (like "Creative") gets a lower-confidence SOLVES edge
     candidate — kept conservative (lower confidence score) since this is
     the weakest signal.

Every relationship carries a `confidence` and short `evidence` string so
downstream consumers (and the demo app's Relationship Explorer) can show
*why* an edge exists — critical for auditability of an inferred graph.
"""

from __future__ import annotations

import re

from src.entity_resolution.resolver import canonicalize_name
from src.schemas.entity import Entity, EntityType
from src.schemas.relationship import Relationship, RelationType
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


def _mentions(haystack: str, needle: str) -> bool:
    """Word-boundary substring check — more precise than plain `in` (avoids
    e.g. 'ai' matching inside 'contain'), while still catching hyphenated
    forms like 'gpt-oss' or 'text-to-image'."""
    if len(needle) < 4:
        return False
    pattern = r"\b" + re.escape(needle) + r"\b"
    return re.search(pattern, haystack) is not None


def _index_by_canonical_name(entities: list[Entity], entity_type: EntityType) -> dict[str, Entity]:
    return {
        canonicalize_name(e.name): e
        for e in entities
        if e.entity_type == entity_type
    }


def map_relationships(entities: list[Entity]) -> list[Relationship]:
    relationships: list[Relationship] = []

    companies = _index_by_canonical_name(entities, EntityType.COMPANY)
    models = [e for e in entities if e.entity_type == EntityType.MODEL]
    repos_and_mcp = [e for e in entities if e.entity_type in (EntityType.REPOSITORY, EntityType.MCP)]
    tools = [e for e in entities if e.entity_type == EntityType.TOOL]
    news_items = [e for e in entities if e.entity_type == EntityType.NEWS]
    videos = [e for e in entities if e.entity_type == EntityType.VIDEO]
    devices_and_robots = [e for e in entities if e.entity_type in (EntityType.DEVICE, EntityType.ROBOT)]
    mcp_entities = [e for e in entities if e.entity_type == EntityType.MCP]
    tasks = [e for e in entities if e.entity_type == EntityType.TASK]
    collections = [e for e in entities if e.entity_type == EntityType.COLLECTION]

    # 1. Company -DEVELOPS-> Model (via provider field matching a company name)
    for model in models:
        provider = (model.model_metadata.provider if model.model_metadata else None) or ""
        key = canonicalize_name(provider)
        company = companies.get(key)
        if company:
            relationships.append(
                Relationship.create(
                    company.id, RelationType.PROVIDES, model.id,
                    confidence=0.95,
                    evidence=f"Model provider field '{provider}' matches company '{company.name}'",
                )
            )

    # 2. Company -DEVELOPS-> Repository/MCP (via GitHub owner login matching company name)
    for repo in repos_and_mcp:
        owner = ""
        if "/" in repo.name:
            owner = repo.name.split("/", 1)[0]
        owner_key = canonicalize_name(owner)
        company = companies.get(owner_key)
        if company is None:
            # Fallback: substring match (e.g. GitHub org "QwenLM" vs company "Qwen")
            for comp_key, comp in companies.items():
                if len(comp_key) >= 4 and (comp_key in owner_key or owner_key in comp_key):
                    company = comp
                    break
        if company:
            relationships.append(
                Relationship.create(
                    company.id, RelationType.DEVELOPS, repo.id,
                    confidence=0.9 if owner_key == canonicalize_name(company.name) else 0.7,
                    evidence=f"Repository owner '{owner}' matches company '{company.name}'",
                )
            )

    # 3. Repository -IMPLEMENTS-> Model (name/description mentions a known model name)
    for repo in repos_and_mcp:
        haystack = f"{repo.name} {repo.description}".lower()
        for model in models:
            model_short_name = model.name.split("/")[-1].lower()
            if _mentions(haystack, model_short_name):
                relationships.append(
                    Relationship.create(
                        repo.id, RelationType.IMPLEMENTS, model.id,
                        confidence=0.7,
                        evidence=f"Repository text mentions model name '{model_short_name}'",
                    )
                )

    # 4. MCP -INTEGRATES_WITH-> Tool (shared category + name/description mention)
    for mcp in mcp_entities:
        haystack = f"{mcp.name} {mcp.description}".lower()
        for tool in tools:
            tool_key = canonicalize_name(tool.name)
            if _mentions(haystack, tool_key):
                relationships.append(
                    Relationship.create(
                        mcp.id, RelationType.INTEGRATES_WITH, tool.id,
                        confidence=0.75,
                        evidence=f"MCP server text mentions tool '{tool.name}'",
                    )
                )

    # 5. Device/Robot -RUNS-> Model (description mentions a known model name)
    for dev in devices_and_robots:
        haystack = f"{dev.name} {dev.description}".lower()
        for model in models:
            model_short_name = model.name.split("/")[-1].lower()
            if _mentions(haystack, model_short_name):
                relationships.append(
                    Relationship.create(
                        dev.id, RelationType.RUNS, model.id,
                        confidence=0.65,
                        evidence=f"Device/robot text mentions model '{model_short_name}'",
                    )
                )

    # 6. News -MENTIONS-> Company (title/summary mentions a known company name)
    for news in news_items:
        haystack = f"{news.name} {news.description}".lower()
        for key, company in companies.items():
            if _mentions(haystack, key):
                relationships.append(
                    Relationship.create(
                        news.id, RelationType.MENTIONS, company.id,
                        confidence=0.8,
                        evidence=f"News text mentions company '{company.name}'",
                    )
                )

    # 6b. News -MENTIONS-> Model (title/summary mentions a known model's short name)
    for news in news_items:
        haystack = f"{news.name} {news.description}".lower()
        for model in models:
            model_short_name = model.name.split("/")[-1].lower()
            if _mentions(haystack, model_short_name):
                relationships.append(
                    Relationship.create(
                        news.id, RelationType.MENTIONS, model.id,
                        confidence=0.75,
                        evidence=f"News text mentions model '{model_short_name}'",
                    )
                )

    # 7. Video -DEMONSTRATES-> Tool (title/description mentions a known tool name)
    for video in videos:
        haystack = f"{video.name} {video.description}".lower()
        for tool in tools:
            tool_key = canonicalize_name(tool.name)
            if _mentions(haystack, tool_key):
                relationships.append(
                    Relationship.create(
                        video.id, RelationType.DEMONSTRATES, tool.id,
                        confidence=0.7,
                        evidence=f"Video text mentions tool '{tool.name}'",
                    )
                )

    # 7b. Video -MENTIONS-> Company (title/description mentions a known company)
    for video in videos:
        haystack = f"{video.name} {video.description}".lower()
        for key, company in companies.items():
            if _mentions(haystack, key):
                relationships.append(
                    Relationship.create(
                        video.id, RelationType.MENTIONS, company.id,
                        confidence=0.7,
                        evidence=f"Video text mentions company '{company.name}'",
                    )
                )

    # 7c. Video -DEMONSTRATES-> Model (title/description mentions a known model's short name)
    for video in videos:
        haystack = f"{video.name} {video.description}".lower()
        for model in models:
            model_short_name = model.name.split("/")[-1].lower()
            if _mentions(haystack, model_short_name):
                relationships.append(
                    Relationship.create(
                        video.id, RelationType.DEMONSTRATES, model.id,
                        confidence=0.7,
                        evidence=f"Video text mentions model '{model_short_name}'",
                    )
                )

    # 7d. Video -DEMONSTRATES-> Repository/MCP (title/description mentions the repo's short name)
    for video in videos:
        haystack = f"{video.name} {video.description}".lower()
        for repo in repos_and_mcp:
            repo_short_name = repo.name.split("/")[-1].lower().replace("-", " ").replace("_", " ")
            if _mentions(haystack, repo_short_name):
                relationships.append(
                    Relationship.create(
                        video.id, RelationType.DEMONSTRATES, repo.id,
                        confidence=0.55,
                        evidence=f"Video text mentions project '{repo.name.split('/')[-1]}'",
                    )
                )

    # 7e. Repository/MCP -MENTIONS-> Company (description text mentions a company,
    #     broader recall than rule 2's owner-login-only match)
    for repo in repos_and_mcp:
        haystack = f"{repo.name} {repo.description}".lower()
        for key, company in companies.items():
            if _mentions(haystack, key):
                relationships.append(
                    Relationship.create(
                        repo.id, RelationType.MENTIONS, company.id,
                        confidence=0.6,
                        evidence=f"Repository text mentions company '{company.name}'",
                    )
                )

    # 8. Tool -SOLVES-> Task (tool description mentions a canonical task name,
    #    e.g. a repo description mentioning "text-to-image" or "summarization",
    #    or the repo's GitHub topics list directly names the task)
    for tool in tools + repos_and_mcp:
        haystack = f"{tool.name} {tool.description}".lower()
        topics = set(tool.repository_metadata.topics) if tool.repository_metadata else set()
        for task in tasks:
            task_key = task.name.lower()
            task_slug = task_key.replace(" ", "-")
            if task_key in haystack or task_slug in haystack or task_slug in topics:
                relationships.append(
                    Relationship.create(
                        tool.id, RelationType.SOLVES, task.id,
                        confidence=0.85 if task_slug in topics else 0.6,
                        evidence=(
                            f"Repository topic '{task_slug}' matches task '{task.name}'"
                            if task_slug in topics
                            else f"Tool text mentions task '{task.name}'"
                        ),
                    )
                )

    # 9. Model -SOLVES-> Task (via modalities/pipeline_tag matching a task name)
    for model in models:
        modalities = model.model_metadata.modalities if model.model_metadata else []
        for modality in modalities:
            modality_name = modality.replace("-", " ")
            for task in tasks:
                if task.name.lower() == modality_name.lower():
                    relationships.append(
                        Relationship.create(
                            model.id, RelationType.SOLVES, task.id,
                            confidence=0.9,
                            evidence=f"Model pipeline tag '{modality}' matches task '{task.name}'",
                        )
                    )

    # Deduplicate relationships by their deterministic id (keep highest confidence)
    dedup: dict[str, Relationship] = {}
    for rel in relationships:
        existing = dedup.get(rel.id)
        if existing is None or rel.confidence > existing.confidence:
            dedup[rel.id] = rel

    result = list(dedup.values())
    logger.info("Relationship mapping complete: %d relationships across %d candidates", len(result), len(relationships))
    return result
