"""Vector Search index builder and query wrapper for the Knowledge Assistant."""

from __future__ import annotations

import json
import logging
from typing import Any

from erp_auto_mapper.core.cdm.registry import CDMRegistry
from erp_auto_mapper.core.entity_hints import ENTITY_HINTS
from erp_auto_mapper.core.mapper.embedding_pass import _ERP_FIELD_ALIASES
from erp_auto_mapper.ka.config import KAConfig

logger = logging.getLogger(__name__)


def build_docs(registry: CDMRegistry | None = None) -> list[dict[str, Any]]:
    """Generate all documents for the Vector Search source Delta table.

    Returns ~470 rows across three doc types:
      - cdm_field:    one per CDM entity field (~150)
      - alias:        one per ERP field alias (~280)
      - entity_hint:  one per ERP table → CDM entity mapping (~40)
    """
    if registry is None:
        registry = CDMRegistry()

    docs: list[dict[str, Any]] = []

    for entity_name in registry.list_entities():
        for field_name, embed_text in registry.get_field_embeddings(entity_name):
            field_type = registry.get_field_type(entity_name, field_name) or "unknown"
            docs.append({
                "doc_id": f"cdm_field::{entity_name}::{field_name}",
                "doc_type": "cdm_field",
                "entity_name": entity_name,
                "field_name": field_name,
                "text": f"{entity_name} | {embed_text}",
                "payload_json": json.dumps({
                    "entity_name": entity_name,
                    "field_name": field_name,
                    "field_type": field_type,
                    "embedding_text": embed_text,
                }),
            })

    for erp_field, cdm_field in _ERP_FIELD_ALIASES.items():
        docs.append({
            "doc_id": f"alias::{erp_field}",
            "doc_type": "alias",
            "entity_name": "",
            "field_name": cdm_field,
            "text": f"ERP field alias: {erp_field} maps to CDM field {cdm_field}",
            "payload_json": json.dumps({
                "erp_field": erp_field,
                "cdm_field": cdm_field,
            }),
        })

    for erp_table_norm, cdm_entity in ENTITY_HINTS.items():
        docs.append({
            "doc_id": f"entity_hint::{erp_table_norm}",
            "doc_type": "entity_hint",
            "entity_name": cdm_entity,
            "field_name": "",
            "text": f"ERP table {erp_table_norm} maps to CDM entity {cdm_entity}",
            "payload_json": json.dumps({
                "erp_table": erp_table_norm,
                "cdm_entity": cdm_entity,
            }),
        })

    return docs


def setup_index(
    spark: Any,
    config: KAConfig | None = None,
    overwrite: bool = False,
) -> None:
    """Create or refresh the ka_vector_docs Delta table and Vector Search index.

    Requires a Spark session and Databricks SDK access.
    """
    if config is None:
        config = KAConfig()

    from databricks.sdk import WorkspaceClient

    docs = build_docs()
    logger.info("Built %d documents for Vector Search index", len(docs))

    df = spark.createDataFrame(docs)
    write_mode = "overwrite" if overwrite else "append"
    df.write.format("delta").mode(write_mode).saveAsTable(config.docs_table_name)
    logger.info("Wrote documents to %s", config.docs_table_name)

    ws = WorkspaceClient()
    vs_client = ws.vector_search

    try:
        vs_client.get_index(config.full_index_name)
        logger.info("Vector Search index %s already exists, syncing...", config.full_index_name)
        vs_client.get_index(config.full_index_name).sync()
    except Exception:
        logger.info("Creating Vector Search index %s", config.full_index_name)
        try:
            vs_client.create_endpoint(name=config.vs_endpoint_name)
        except Exception:
            logger.info("VS endpoint %s already exists", config.vs_endpoint_name)

        vs_client.create_index(
            name=config.full_index_name,
            endpoint_name=config.vs_endpoint_name,
            primary_key="doc_id",
            index_type="DELTA_SYNC",
            delta_sync_index_spec={
                "source_table": config.docs_table_name,
                "embedding_source_columns": [{"name": "text"}],
                "pipeline_type": "TRIGGERED",
            },
        )
        logger.info("Created Vector Search index %s", config.full_index_name)


def query_index(
    query: str,
    config: KAConfig | None = None,
    entity_filter: str | None = None,
    num_results: int | None = None,
) -> list[dict[str, Any]]:
    """Query the Vector Search index and return decoded results."""
    if config is None:
        config = KAConfig()

    from databricks.sdk import WorkspaceClient

    ws = WorkspaceClient()
    index = ws.vector_search.get_index(config.full_index_name)

    filters: dict[str, str] = {}
    if entity_filter:
        filters["entity_name"] = entity_filter

    results = index.similarity_search(
        query_text=query,
        columns=["doc_id", "doc_type", "entity_name", "field_name", "text", "payload_json"],
        num_results=num_results or config.vs_num_results,
        filters=filters if filters else None,
    )

    parsed: list[dict[str, Any]] = []
    for row in results.get("result", {}).get("data_array", []):
        doc = {
            "doc_id": row[0],
            "doc_type": row[1],
            "entity_name": row[2],
            "field_name": row[3],
            "text": row[4],
        }
        try:
            doc["payload"] = json.loads(row[5])
        except (json.JSONDecodeError, IndexError):
            doc["payload"] = {}
        if len(row) > 6:
            doc["score"] = row[6]
        parsed.append(doc)

    return parsed
