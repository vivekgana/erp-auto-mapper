"""CDM entity management — register custom entities and list all."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import Field, create_model

from erp_auto_mapper.api.auth import get_current_user
from erp_auto_mapper.api.models.requests import CDMRegisterRequest
from erp_auto_mapper.api.models.responses import CDMEntityInfo, CDMRegisterResponse
from erp_auto_mapper.core.cdm.entities import CDMBase
from erp_auto_mapper.core.cdm.registry import CDMRegistry

router = APIRouter(prefix="/v1/cdm", tags=["cdm"])

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "date": str,
    "decimal": float,
    "integer": int,
    "boolean": bool,
}


def _get_registry(request: Request) -> CDMRegistry:
    if not hasattr(request.app.state, "cdm_registry"):
        request.app.state.cdm_registry = CDMRegistry()
    registry: CDMRegistry = request.app.state.cdm_registry
    return registry


@router.post("/register", response_model=CDMRegisterResponse, status_code=201)
async def register_entity(
    req: CDMRegisterRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> CDMRegisterResponse:
    registry = _get_registry(request)

    field_defs: dict[str, Any] = {}
    for f in req.fields:
        py_type = _TYPE_MAP.get(f.type, str)
        field_defs[f.name] = (
            Optional[py_type],
            Field(default=None, description=f.description),
        )

    dynamic_model = create_model(req.entity_name, __base__=CDMBase, **field_defs)
    registry.register_entity(req.entity_name, dynamic_model, version=req.cdm_version)

    return CDMRegisterResponse(
        entity_name=req.entity_name,
        cdm_version=req.cdm_version,
        field_count=len(req.fields),
    )


@router.get("/entities", response_model=list[CDMEntityInfo])
async def list_entities(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
) -> list[CDMEntityInfo]:
    registry = _get_registry(request)
    result = []
    for name in registry.list_entities():
        field_names = registry.get_all_field_names(name)
        fields = []
        for fname in field_names:
            ftype = registry.get_field_type(name, fname) or "string"
            fields.append({"name": fname, "type": ftype})
        result.append(CDMEntityInfo(name=name, fields=fields))
    return result
