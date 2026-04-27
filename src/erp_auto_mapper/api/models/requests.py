"""API request schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FieldDef(BaseModel):
    name: str
    type: str = "string"
    description: str = ""


class EntityDef(BaseModel):
    name: str
    fields: list[FieldDef]


class GoldenEntry(BaseModel):
    source: str
    cdm: str


class MapRequest(BaseModel):
    engagement_id: str
    erp_type: str = "generic"
    entities: list[EntityDef]
    llm_endpoint: str | None = None
    golden_set: list[GoldenEntry] = Field(default_factory=list)
    cdm_version: str = "1.0.0"


class ValidateRequest(BaseModel):
    engagement_id: str
    mappings: list[dict[str, Any]]
    golden_set: list[GoldenEntry] = Field(default_factory=list)


class CDMRegisterRequest(BaseModel):
    entity_name: str
    cdm_version: str = "1.0.0"
    fields: list[FieldDef]
