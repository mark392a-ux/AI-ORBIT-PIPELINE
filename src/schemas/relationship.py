"""
Relationship schema — models directed, typed edges between two entities in
the AI Orbit knowledge graph.

Relationships are also given deterministic IDs (UUID5 of
source_id+predicate+target_id) so that re-running the relationship-mapping
stage on unchanged input never produces duplicate edges.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, Field

from src.schemas.entity import AI_ORBIT_NAMESPACE


class RelationType(str, Enum):
    DEVELOPS = "develops"          # Company -> Tool/Model/Device/Robot
    SOLVES = "solves"               # Tool -> Task
    INTEGRATES_WITH = "integrates_with"  # MCP -> Tool
    RUNS = "runs"                    # Device/Robot -> Model
    IMPLEMENTS = "implements"        # Repository -> Model
    PUBLISHES = "publishes"          # Company -> News
    DEMONSTRATES = "demonstrates"    # Video -> Tool/Model
    MEMBER_OF = "member_of"          # Entity -> Collection
    MENTIONS = "mentions"            # News -> Company/Tool/Model
    PROVIDES = "provides"            # Company -> Model (as hosting provider)
    FORKS_FROM = "forks_from"        # Repository -> Repository
    USES = "uses"                    # Tool -> Model


class Relationship(BaseModel):
    id: str
    source_id: str = Field(..., description="Entity.id of the subject")
    predicate: RelationType
    target_id: str = Field(..., description="Entity.id of the object")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    evidence: str = Field("", description="Short human-readable justification")

    @staticmethod
    def generate_id(source_id: str, predicate: str, target_id: str) -> str:
        seed = f"{source_id}::{predicate}::{target_id}"
        return str(uuid.uuid5(AI_ORBIT_NAMESPACE, seed))

    @classmethod
    def create(
        cls,
        source_id: str,
        predicate: RelationType,
        target_id: str,
        confidence: float = 1.0,
        evidence: str = "",
    ) -> "Relationship":
        return cls(
            id=cls.generate_id(source_id, predicate.value, target_id),
            source_id=source_id,
            predicate=predicate,
            target_id=target_id,
            confidence=confidence,
            evidence=evidence,
        )
