"""POST /v1/map — map ERP schema to CDM."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from erp_auto_mapper.api.auth import get_current_user
from erp_auto_mapper.api.models.requests import MapRequest
from erp_auto_mapper.api.models.responses import (
    EntityMappingResponse,
    FieldMappingResponse,
    MapResponse,
)
from erp_auto_mapper.core.cdm.registry import CDMRegistry
from erp_auto_mapper.core.extractors.base import EntityMetadata, ERPMetadata, ERPType, FieldMetadata
from erp_auto_mapper.core.mapper.embedding_pass import EmbeddingMappingPass, MappingCandidate
from erp_auto_mapper.core.mapper.ensemble import MappingResult
from erp_auto_mapper.core.entity_hints import ENTITY_HINTS, token_overlap

router = APIRouter(prefix="/v1", tags=["mapping"])


def _count_fields(req: MapRequest) -> int:
    return sum(len(e.fields) for e in req.entities)


def _to_erp_metadata(req: MapRequest) -> ERPMetadata:
    entities = []
    for e in req.entities:
        fields = [FieldMetadata(name=f.name, type=f.type, description=f.description) for f in e.fields]
        entities.append(EntityMetadata(name=e.name, fields=fields))
    try:
        erp_type = ERPType(req.erp_type.lower())
    except ValueError:
        erp_type = ERPType.SAP
    return ERPMetadata(source=erp_type, entities=entities)


def _resolve_entity(entity_name: str, cdm: CDMRegistry) -> str | None:
    normalized = entity_name.lower().replace(" ", "").replace("_", "")
    hint = ENTITY_HINTS.get(normalized)
    cdm_names = cdm.list_entities()
    if hint and hint in cdm_names:
        return hint
    best_score, best_name = 0.0, None
    for name in cdm_names:
        score = token_overlap(entity_name, name)
        if score > best_score:
            best_score, best_name = score, name
    return best_name if best_score > 0.3 else (cdm_names[0] if cdm_names else None)


def _best_per_field(candidates: list[MappingCandidate]) -> dict[str, MappingCandidate]:
    best: dict[str, MappingCandidate] = {}
    for c in candidates:
        existing = best.get(c.source_field)
        if existing is None or c.score > existing.score:
            best[c.source_field] = c
    return best


@router.post("/map", response_model=MapResponse)
async def map_fields(req: MapRequest, request: Request, user: dict[str, Any] = Depends(get_current_user)) -> MapResponse:
    rate_limiter = request.app.state.rate_limiter
    tenant_id = user.get("tenant_id", user.get("sub", "anonymous"))

    rate_limiter.check_field_count(_count_fields(req))
    rate_limiter.check_request_count(tenant_id)

    cdm = CDMRegistry()
    metadata = _to_erp_metadata(req)
    embedding_pass = EmbeddingMappingPass()

    entity_mappings: list[EntityMappingResponse] = []

    for entity in metadata.entities:
        cdm_entity = _resolve_entity(entity.name, cdm)
        if not cdm_entity:
            continue

        candidates = embedding_pass.map_fields(entity.fields, cdm_entity)
        best = _best_per_field(candidates)

        field_responses = []
        for src_field, mc in best.items():
            band = MappingResult.classify_confidence(mc.score)
            cdm_type = cdm.get_field_type(cdm_entity, mc.cdm_field) or "string"
            field_responses.append(
                FieldMappingResponse(
                    source_field=mc.source_field,
                    cdm_field=mc.cdm_field,
                    confidence=mc.score,
                    band=band.value,
                    method=mc.method,
                    source_type=next(
                        (f.type for f in entity.fields if f.name == mc.source_field), "string"
                    ),
                    cdm_type=cdm_type,
                )
            )

        entity_mappings.append(
            EntityMappingResponse(
                source_entity=entity.name,
                cdm_entity=cdm_entity,
                field_mappings=field_responses,
            )
        )

    session_key = f"{tenant_id}::{req.engagement_id}"
    session_cache = request.app.state.session_cache
    session_cache.put(tenant_id, req.engagement_id, {"entity_mappings": len(entity_mappings)})

    return MapResponse(
        engagement_id=req.engagement_id,
        entity_mappings=entity_mappings,
        session_state_key=session_key,
    )
