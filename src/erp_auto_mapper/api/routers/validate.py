"""POST /v1/validate — run 6-dimension eval on existing mappings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from erp_auto_mapper.api.auth import get_current_user
from erp_auto_mapper.api.models.requests import ValidateRequest
from erp_auto_mapper.api.models.responses import (
    EvalDimensions,
    EvalReportResponse,
    ValidateResponse,
)
from erp_auto_mapper.core.eval.mapping_scorer import (
    FieldMapping,
    MappingResult as ScorerMappingResult,
    MappingScorer,
)

router = APIRouter(prefix="/v1", tags=["validation"])


@router.post("/validate", response_model=ValidateResponse)
async def validate_mappings(
    req: ValidateRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> ValidateResponse:
    rate_limiter = request.app.state.rate_limiter
    tenant_id = user.get("tenant_id", user.get("sub", "anonymous"))
    rate_limiter.check_request_count(tenant_id)

    scorer = MappingScorer()

    all_field_mappings = []
    for m in req.mappings:
        for fm in m.get("field_mappings", []):
            all_field_mappings.append(
                FieldMapping(
                    source_field=fm.get("source_field", ""),
                    target_field=fm.get("target_field", fm.get("cdm_field", "")),
                    source_type=fm.get("source_type", "string"),
                    target_type=fm.get("cdm_type", fm.get("target_type", "string")),
                    confidence=fm.get("confidence", 0.0),
                )
            )

    mapping_result = ScorerMappingResult(
        source_entity="input",
        target_entity="cdm",
        field_mappings=all_field_mappings,
    )
    result = scorer.score(mapping_result)

    dims = result.per_dimension

    return ValidateResponse(
        engagement_id=req.engagement_id,
        eval_report=EvalReportResponse(
            aggregate=result.aggregate,
            per_dimension=EvalDimensions(
                semantic_similarity=dims.get("semantic_similarity", 0.0),
                type_compatibility=dims.get("type_compatibility", 0.0),
                value_distribution_overlap=dims.get("value_distribution_overlap", 0.0),
                llm_judge_score=dims.get("llm_judge_score", 0.0),
                business_rule_compliance=dims.get("business_rule_compliance", 0.0),
                golden_set_match=dims.get("golden_set_match", 0.0),
            ),
            gate_passed=result.aggregate >= 0.85,
        ),
    )
