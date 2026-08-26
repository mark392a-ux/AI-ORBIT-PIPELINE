"""
Core entity schema for the AI Orbit ecosystem dataset.

Every record produced by any extractor is coerced into an `Entity` before it
is allowed to progress further down the pipeline. This is the single
contract that cleaning, normalization, dedup, classification, and
relationship-mapping all rely on.

Design notes
------------
- `id` is a deterministic UUID5 derived from (entity_type, canonical_url or
  canonical_name). This means re-running the pipeline on the same source
  data always yields the same IDs — a requirement called out explicitly in
  the spec ("stable-generated-uuid").
- Specialized metadata (ModelMetadata, RepositoryMetadata, etc.) is modeled
  as optional, typed sub-objects rather than a loose dict, so validation is
  meaningful and downstream code gets autocomplete/type-checking instead of
  guessing key names.
- `source` is mandatory and traceable: every entity must point back to
  where it was found, in line with the "never hallucinate" rule — if we
  can't cite a source, the record does not go in the dataset.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator

# Namespace UUID for deterministic UUID5 generation. Fixed and never
# changed, so IDs are stable across pipeline runs and across machines.
AI_ORBIT_NAMESPACE = uuid.UUID("6f1c1a0e-6b8b-4e3a-9b8b-1f7f2b8a9c10")


class EntityType(str, Enum):
    TOOL = "Tool"
    TASK = "Task"
    COMPANY = "Company"
    NEWS = "News"
    VIDEO = "Video"
    ROBOT = "Robot"
    DEVICE = "Device"
    MODEL = "Model"
    REPOSITORY = "Repository"
    MCP = "MCP"
    COLLECTION = "Collection"
    PERSONAL = "Personal"
    CREATIVE = "Creative"


class SourceInfo(BaseModel):
    """Provenance record — where this entity's data actually came from."""

    name: str = Field(..., description="Human-readable source name, e.g. 'GitHub API'")
    url: str = Field(..., description="Canonical URL of the source record")


class ModelMetadata(BaseModel):
    license: Optional[str] = None
    modalities: list[str] = Field(default_factory=list)
    provider: Optional[str] = None
    downloads: Optional[int] = None
    likes: Optional[int] = None
    library: Optional[str] = None


class RepositoryMetadata(BaseModel):
    stars: Optional[int] = None
    forks: Optional[int] = None
    primary_language: Optional[str] = None
    last_updated: Optional[str] = None
    open_issues: Optional[int] = None
    license: Optional[str] = None
    topics: list[str] = Field(default_factory=list)


class MCPMetadata(BaseModel):
    installation_methods: list[str] = Field(default_factory=list)
    runtime_requirements: list[str] = Field(default_factory=list)
    transport: Optional[str] = None  # e.g. stdio, sse, http


class CompanyMetadata(BaseModel):
    founding_year: Optional[int] = None
    industry_sector: Optional[str] = None
    headquarters: Optional[str] = None
    employee_range: Optional[str] = None


class VideoMetadata(BaseModel):
    channel: Optional[str] = None
    published_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    view_count: Optional[int] = None


class NewsMetadata(BaseModel):
    published_at: Optional[str] = None
    publisher: Optional[str] = None


class Entity(BaseModel):
    id: str = Field(..., description="Deterministic UUID5")
    entity_type: EntityType
    name: str
    description: str = ""
    url: str
    categories: list[str] = Field(default_factory=list)
    source: SourceInfo

    # Specialized metadata — only the relevant one(s) will be populated.
    model_metadata: Optional[ModelMetadata] = None
    repository_metadata: Optional[RepositoryMetadata] = None
    mcp_metadata: Optional[MCPMetadata] = None
    company_metadata: Optional[CompanyMetadata] = None
    video_metadata: Optional[VideoMetadata] = None
    news_metadata: Optional[NewsMetadata] = None

    # Pipeline bookkeeping (not part of the "required" schema but useful
    # for auditability and the "New/Recently added" category).
    ingested_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_recent: bool = False

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Entity name cannot be blank")
        return v

    @staticmethod
    def generate_id(entity_type: EntityType | str, key: str) -> str:
        """Deterministic UUID5 from entity type + canonical key (URL or name)."""
        etype = entity_type.value if isinstance(entity_type, EntityType) else entity_type
        seed = f"{etype.lower()}::{key.strip().lower()}"
        return str(uuid.uuid5(AI_ORBIT_NAMESPACE, seed))

    def to_common_schema(self) -> dict:
        """Return only the fields required by the spec's common schema."""
        return {
            "id": self.id,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "categories": self.categories,
            "source": self.source.model_dump(),
        }
