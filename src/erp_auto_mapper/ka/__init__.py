"""ERP Auto Mapper Knowledge Assistant."""

from erp_auto_mapper.ka.agent import ERPKnowledgeAssistant, log_agent
from erp_auto_mapper.ka.config import KAConfig
from erp_auto_mapper.ka.skills import (
    get_entity_schema,
    get_historical_mappings,
    list_cdm_entities,
    lookup_alias,
    resolve_entity,
    run_mapping,
    search_cdm_fields,
)
from erp_auto_mapper.ka.vector_index import build_docs, query_index, setup_index

__all__ = [
    "ERPKnowledgeAssistant",
    "KAConfig",
    "build_docs",
    "get_entity_schema",
    "get_historical_mappings",
    "list_cdm_entities",
    "log_agent",
    "lookup_alias",
    "query_index",
    "resolve_entity",
    "run_mapping",
    "search_cdm_fields",
    "setup_index",
]
