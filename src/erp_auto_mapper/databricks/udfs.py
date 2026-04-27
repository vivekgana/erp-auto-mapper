"""Unity Catalog Python UDF registration for map_fields and validate_quality."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _map_fields_impl(schema_json: str, erp_type: str, cdm_entity: str) -> str:
    """Map ERP fields to CDM. Returns JSON string of mapping candidates."""
    from erp_auto_mapper.core.extractors.base import FieldMetadata
    from erp_auto_mapper.core.mapper.embedding_pass import EmbeddingMappingPass
    from erp_auto_mapper.core.mapper.ensemble import MappingResult

    fields_raw = json.loads(schema_json)
    fields = [FieldMetadata(name=f["name"], type=f.get("type", "string")) for f in fields_raw]

    embedding = EmbeddingMappingPass()
    candidates = embedding.map_fields(fields, cdm_entity)

    best: dict[str, Any] = {}
    for c in candidates:
        existing = best.get(c.source_field)
        if existing is None or c.score > existing.score:
            best[c.source_field] = c

    output = [
        {
            "source_field": mc.source_field,
            "cdm_field": mc.cdm_field,
            "confidence": round(mc.score, 4),
            "band": MappingResult.classify_confidence(mc.score).value,
        }
        for mc in best.values()
    ]
    return json.dumps(output)


def _validate_quality_impl(mappings_json: str) -> float:
    """Returns aggregate eval score as DOUBLE in [0, 1]."""
    from erp_auto_mapper.core.eval.mapping_scorer import MappingInput, MappingScorer

    mappings = json.loads(mappings_json)
    scorer = MappingScorer()

    if isinstance(mappings, list):
        total = 0.0
        for m in mappings:
            inp = MappingInput(
                source_field=m.get("source_field", ""),
                cdm_field=m.get("cdm_field", ""),
                mapping_confidence=m.get("confidence", 0.0),
                source_type=m.get("source_type", ""),
                cdm_type=m.get("cdm_type", ""),
            )
            result = scorer.score(inp)
            total += result.aggregate
        return round(total / len(mappings), 4) if mappings else 0.0
    else:
        inp = MappingInput(
            source_field=mappings.get("source_field", ""),
            cdm_field=mappings.get("cdm_field", ""),
            mapping_confidence=mappings.get("confidence", 0.0),
        )
        return round(scorer.score(inp).aggregate, 4)


_MAP_FIELDS_UDF_SQL = """
import json

def map_fields_fn(schema_json, erp_type, cdm_entity):
    from erp_auto_mapper.core.cdm.registry import CDMRegistry
    from erp_auto_mapper.core.extractors.base import FieldMetadata
    from erp_auto_mapper.core.mapper.embedding_pass import EmbeddingMappingPass
    from erp_auto_mapper.core.mapper.ensemble import MappingResult

    fields_raw = json.loads(schema_json)
    fields = [FieldMetadata(name=f["name"], type=f.get("type", "string")) for f in fields_raw]
    cdm = CDMRegistry()
    embedding = EmbeddingMappingPass()
    candidates = embedding.map_fields(fields, cdm_entity)
    best = {}
    for c in candidates:
        if c.source_field not in best or c.score > best[c.source_field].score:
            best[c.source_field] = c
    output = [{"source_field": mc.source_field, "cdm_field": mc.cdm_field, "confidence": round(mc.score, 4), "band": MappingResult.classify_confidence(mc.score).value} for mc in best.values()]
    return json.dumps(output)

return map_fields_fn(schema_json, erp_type, cdm_entity)
"""

_VALIDATE_QUALITY_UDF_SQL = """
import json

def validate_fn(mappings_json):
    from erp_auto_mapper.core.eval.mapping_scorer import MappingInput, MappingScorer
    mappings = json.loads(mappings_json)
    scorer = MappingScorer()
    if isinstance(mappings, list):
        total = 0.0
        for m in mappings:
            inp = MappingInput(source_field=m.get("source_field",""), cdm_field=m.get("cdm_field",""), mapping_confidence=m.get("confidence",0.0))
            total += scorer.score(inp).aggregate
        return round(total / len(mappings), 4) if mappings else 0.0
    inp = MappingInput(source_field=mappings.get("source_field",""), cdm_field=mappings.get("cdm_field",""), mapping_confidence=mappings.get("confidence",0.0))
    return round(scorer.score(inp).aggregate, 4)

return validate_fn(mappings_json)
"""


def register_udfs(catalog: str = "erp_auto_mapper_dev", schema: str = "mapper", warehouse_id: str = "") -> None:
    """Register map_fields and validate_quality as UC Python UDFs."""
    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient()
    fqn_map = f"{catalog}.{schema}.map_fields"
    fqn_val = f"{catalog}.{schema}.validate_quality"

    logger.info("Registering UDFs: %s, %s", fqn_map, fqn_val)

    ws.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=f"""
        CREATE OR REPLACE FUNCTION {fqn_map}(schema_json STRING, erp_type STRING, cdm_entity STRING)
        RETURNS STRING
        LANGUAGE PYTHON
        AS $${_MAP_FIELDS_UDF_SQL}$$
        """,
        catalog=catalog,
        schema=schema,
    )

    ws.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=f"""
        CREATE OR REPLACE FUNCTION {fqn_val}(mappings_json STRING)
        RETURNS DOUBLE
        LANGUAGE PYTHON
        AS $${_VALIDATE_QUALITY_UDF_SQL}$$
        """,
        catalog=catalog,
        schema=schema,
    )

    logger.info("UDFs registered successfully")


def register_udfs_cli() -> None:
    """CLI entry point for UDF registration."""
    import argparse

    parser = argparse.ArgumentParser(description="Register ERP Auto Mapper UDFs")
    parser.add_argument("--catalog", default="erp_auto_mapper_dev")
    parser.add_argument("--schema", default="mapper")
    parser.add_argument("--warehouse-id", required=True, help="SQL warehouse ID for statement execution")
    args = parser.parse_args()
    register_udfs(catalog=args.catalog, schema=args.schema, warehouse_id=args.warehouse_id)
