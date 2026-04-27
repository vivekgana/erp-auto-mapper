"""Knowledge Assistant skill functions — registered as tools with the Databricks AI Agent."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from erp_auto_mapper.core.cdm.registry import CDMRegistry
from erp_auto_mapper.core.entity_hints import ENTITY_HINTS, token_overlap
from erp_auto_mapper.core.mapper.embedding_pass import _ERP_FIELD_ALIASES, _camel_to_snake
from erp_auto_mapper.ka.config import KAConfig

logger = logging.getLogger(__name__)

_registry = CDMRegistry()


def search_cdm_fields(
    query: str,
    entity_filter: str | None = None,
    config: KAConfig | None = None,
) -> list[dict[str, Any]]:
    """Search the CDM field catalog using semantic similarity.

    Args:
        query: Natural language or field name to search for.
        entity_filter: Optional CDM entity name to restrict results.

    Returns:
        List of matching CDM fields with entity_name, field_name, field_type, and score.
    """
    from erp_auto_mapper.ka.vector_index import query_index

    if config is None:
        config = KAConfig()

    results = query_index(query, config, entity_filter=entity_filter)
    return [
        {
            "entity_name": r.get("entity_name", ""),
            "field_name": r.get("field_name", ""),
            "field_type": r.get("payload", {}).get("field_type", ""),
            "text": r.get("text", ""),
            "score": r.get("score", 0.0),
        }
        for r in results
        if r.get("doc_type") == "cdm_field"
    ]


def lookup_alias(source_field: str) -> dict[str, Any]:
    """Check the ERP field alias table for a direct CDM mapping.

    Args:
        source_field: ERP field name (exact or CamelCase — normalized internally).

    Returns:
        Dict with found (bool), cdm_field, and source_field.
    """
    normalized = _camel_to_snake(source_field).lower().replace(" ", "").replace("-", "_")
    cdm_field = _ERP_FIELD_ALIASES.get(normalized, "")
    return {
        "found": bool(cdm_field),
        "cdm_field": cdm_field,
        "source_field": source_field,
        "normalized_as": normalized,
    }


def resolve_entity(erp_table_name: str) -> dict[str, Any]:
    """Resolve an ERP table name to its CDM entity using hints and token overlap.

    Args:
        erp_table_name: Raw ERP table name (e.g. "BKPF", "GL_JOURNALS").

    Returns:
        Dict with found, cdm_entity, method, score, and ranked candidates.
    """
    normalized = erp_table_name.lower().replace(" ", "").replace("_", "")
    hint = ENTITY_HINTS.get(normalized)
    if hint:
        return {
            "found": True,
            "cdm_entity": hint,
            "method": "hint",
            "score": 1.0,
            "candidates": [hint],
        }

    all_entities = _registry.list_entities()
    scored = []
    for entity in all_entities:
        score = token_overlap(erp_table_name, entity)
        if score > 0:
            scored.append((entity, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    if scored and scored[0][1] >= 0.2:
        return {
            "found": True,
            "cdm_entity": scored[0][0],
            "method": "token_overlap",
            "score": scored[0][1],
            "candidates": [e for e, _ in scored],
        }

    return {
        "found": False,
        "cdm_entity": "",
        "method": "none",
        "score": 0.0,
        "candidates": [e for e, _ in scored] if scored else all_entities,
    }


def run_mapping(
    source_fields: list[dict[str, str]],
    erp_type: str,
    entity_name: str,
    engagement_id: str | None = None,
) -> dict[str, Any]:
    """Run the full 3-pass ERP-to-CDM mapping for a set of source fields.

    Args:
        source_fields: List of {"name": str, "type": str, "description": str} dicts.
        erp_type: ERP system identifier (e.g. "sap", "oracle").
        entity_name: Source entity name (e.g. "BKPF").
        engagement_id: Optional run identifier.

    Returns:
        Dict with engagement_id, cdm_entity, field_mappings, and stats.
    """
    from erp_auto_mapper.core.extractors.base import (
        EntityMetadata,
        ERPMetadata,
        ERPType,
        FieldMetadata,
    )
    from erp_auto_mapper.core.orchestrator import ERPMappingOrchestrator, OrchestratorConfig

    eng_id = engagement_id or f"ka-{uuid.uuid4().hex[:8]}"

    fields = [
        FieldMetadata(
            name=f["name"],
            type=f.get("type", "string"),
            description=f.get("description", ""),
        )
        for f in source_fields
    ]
    metadata = ERPMetadata(
        source=ERPType(erp_type.lower()),
        entities=[EntityMetadata(name=entity_name, fields=fields)],
    )
    config = OrchestratorConfig(
        engagement_id=eng_id,
        skip_eval=True,
        source_erp_type=erp_type.lower(),
    )
    orchestrator = ERPMappingOrchestrator(config=config)
    result = asyncio.run(orchestrator.run(metadata))

    if not result.entity_mappings:
        return {
            "engagement_id": eng_id,
            "cdm_entity": "",
            "field_mappings": [],
            "stats": {"auto": 0, "review": 0, "manual": 0, "avg_confidence": 0.0},
        }

    em = result.entity_mappings[0]
    bands = {"auto": 0, "review": 0, "manual": 0}
    total_conf = 0.0
    for fm in em.field_mappings:
        band = fm.get("band", "manual")
        bands[band] = bands.get(band, 0) + 1
        total_conf += fm.get("confidence", 0.0)

    avg_conf = total_conf / len(em.field_mappings) if em.field_mappings else 0.0

    return {
        "engagement_id": eng_id,
        "cdm_entity": em.cdm_entity,
        "field_mappings": em.field_mappings,
        "stats": {**bands, "avg_confidence": round(avg_conf, 3)},
    }


def get_historical_mappings(
    source_field: str,
    erp_type: str | None = None,
    limit: int = 10,
    config: KAConfig | None = None,
) -> list[dict[str, Any]]:
    """Query the erp_mapping_results Delta table for past mappings of a source field.

    Args:
        source_field: ERP field name to look up.
        erp_type: Optional ERP system filter.
        limit: Max rows to return.

    Returns:
        List of historical mapping rows. Empty if table is unreachable.
    """
    if config is None:
        config = KAConfig()

    try:
        from erp_auto_mapper.databricks.delta_client import DeltaClient

        client = DeltaClient(
            warehouse_id=config.warehouse_id,
            catalog=config.catalog,
            schema=config.schema_name,
        )
        where = f"source_field = '{source_field}'"
        if erp_type:
            where += f" AND erp_type = '{erp_type}'"

        table = f"{config.catalog}.{config.schema_name}.erp_mapping_results"
        sql = f"SELECT * FROM {table} WHERE {where} ORDER BY mapped_at DESC LIMIT {limit}"
        return client.execute_sql(sql)
    except Exception as exc:
        logger.warning("Could not query historical mappings: %s", exc)
        return []


def list_cdm_entities() -> list[str]:
    """List all CDM entities available in the registry.

    Returns:
        Sorted list of CDM entity names.
    """
    return _registry.list_entities()


def get_entity_schema(entity_name: str) -> dict[str, Any]:
    """Return the full field list and types for a CDM entity.

    Args:
        entity_name: CDM entity name (case-sensitive, e.g. "JournalEntry").

    Returns:
        Dict with entity_name, found, fields list, and field_count.
    """
    embeddings = _registry.get_field_embeddings(entity_name)
    if not embeddings:
        return {
            "entity_name": entity_name,
            "found": False,
            "fields": [],
            "field_count": 0,
        }

    fields = []
    for field_name, embed_text in embeddings:
        field_type = _registry.get_field_type(entity_name, field_name) or "unknown"
        description = ""
        parts = embed_text.split(" | ")
        if len(parts) >= 3:
            description = parts[2]
        fields.append({
            "name": field_name,
            "type": field_type,
            "description": description,
        })

    return {
        "entity_name": entity_name,
        "found": True,
        "fields": fields,
        "field_count": len(fields),
    }
