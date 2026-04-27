"""API response schemas."""

from __future__ import annotations


from pydantic import BaseModel, Field


class FieldMappingResponse(BaseModel):
    source_field: str
    cdm_field: str
    confidence: float
    band: str
    method: str = ""
    source_type: str = "string"
    cdm_type: str = "string"
    transform_expression: str = "direct"
    rationale: str = ""


class EntityMappingResponse(BaseModel):
    source_entity: str
    cdm_entity: str
    field_mappings: list[FieldMappingResponse]


class EvalDimensions(BaseModel):
    semantic_similarity: float = 0.0
    type_compatibility: float = 0.0
    value_distribution_overlap: float = 0.0
    llm_judge_score: float = 0.0
    business_rule_compliance: float = 0.0
    golden_set_match: float = 0.0


class GoldenSetMetrics(BaseModel):
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


class EvalReportResponse(BaseModel):
    aggregate: float
    per_dimension: EvalDimensions = Field(default_factory=EvalDimensions)
    fields_passed: int = 0
    total_fields: int = 0
    gate_passed: bool = False
    golden_set: GoldenSetMetrics = Field(default_factory=GoldenSetMetrics)


class MapResponse(BaseModel):
    engagement_id: str
    entity_mappings: list[EntityMappingResponse]
    eval_report: EvalReportResponse | None = None
    session_state_key: str = ""


class ValidateResponse(BaseModel):
    engagement_id: str
    eval_report: EvalReportResponse


class CDMEntityInfo(BaseModel):
    name: str
    fields: list[dict[str, str]]
    version: str = "1.0.0"


class CDMRegisterResponse(BaseModel):
    entity_name: str
    cdm_version: str
    field_count: int


class ErrorResponse(BaseModel):
    detail: str
