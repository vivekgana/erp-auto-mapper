# Databricks notebook source
# MAGIC %md
# MAGIC # ERP Auto Mapper — Quick Start
# MAGIC Map any ERP schema to the Canonical Data Model in under 20 lines.

# COMMAND ----------

import asyncio
from erp_auto_mapper import CDMRegistry, ERPMappingOrchestrator, OrchestratorConfig
from erp_auto_mapper.core.extractors.base import EntityMetadata, ERPMetadata, ERPType, FieldMetadata

# COMMAND ----------

fields = [
    FieldMetadata(name="BUKRS", type="string", description="Company Code"),
    FieldMetadata(name="BELNR", type="string", description="Document Number"),
    FieldMetadata(name="BLDAT", type="date", description="Document Date"),
    FieldMetadata(name="BUDAT", type="date", description="Posting Date"),
    FieldMetadata(name="WAERS", type="string", description="Currency"),
]

metadata = ERPMetadata(
    source=ERPType.SAP,
    entities=[EntityMetadata(name="BKPF", fields=fields)],
)

# COMMAND ----------

config = OrchestratorConfig(engagement_id="quickstart-demo")
orchestrator = ERPMappingOrchestrator(config=config)
result = asyncio.run(orchestrator.run(metadata))

# COMMAND ----------

for em in result.entity_mappings:
    print(f"\n{em.source_entity} -> {em.cdm_entity}")
    for fm in em.field_mappings:
        print(f"  {fm['source_field']:20s} -> {fm['cdm_field']:20s}  ({fm['confidence']:.2f} {fm['band']})")
