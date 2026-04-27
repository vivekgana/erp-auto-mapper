# Databricks notebook source
# MAGIC %md
# MAGIC # Oracle ERP -> CDM Walkthrough
# MAGIC Maps Oracle ERP Cloud schema to the Canonical Data Model.

# COMMAND ----------

import asyncio
from erp_auto_mapper import CDMRegistry, ERPMappingOrchestrator, OrchestratorConfig
from erp_auto_mapper.core.extractors.base import EntityMetadata, ERPMetadata, ERPType, FieldMetadata

# COMMAND ----------

oracle_fields = [
    FieldMetadata(name="LEDGER_ID", type="string", description="Ledger Identifier"),
    FieldMetadata(name="CODE_COMBINATION_ID", type="string", description="GL Account"),
    FieldMetadata(name="ACCOUNTING_DATE", type="date", description="Accounting Date"),
    FieldMetadata(name="ENTERED_DR", type="decimal", description="Entered Debit Amount"),
    FieldMetadata(name="ENTERED_CR", type="decimal", description="Entered Credit Amount"),
    FieldMetadata(name="CURRENCY_CODE", type="string", description="Transaction Currency"),
    FieldMetadata(name="JE_HEADER_ID", type="string", description="Journal Header ID"),
    FieldMetadata(name="PERIOD_NAME", type="string", description="Accounting Period"),
]

metadata = ERPMetadata(
    source=ERPType.ORACLE,
    entities=[EntityMetadata(name="GL_JE_LINES", fields=oracle_fields)],
)
print(f"Schema: {len(metadata.entities)} entities, {metadata.field_count()} fields")

# COMMAND ----------

config = OrchestratorConfig(engagement_id="oracle-walkthrough")
orchestrator = ERPMappingOrchestrator(config=config)
result = asyncio.run(orchestrator.run(metadata))

# COMMAND ----------

for em in result.entity_mappings:
    auto = sum(1 for fm in em.field_mappings if fm["band"] == "auto")
    review = sum(1 for fm in em.field_mappings if fm["band"] == "review")
    manual = sum(1 for fm in em.field_mappings if fm["band"] == "manual")
    print(f"{em.source_entity} -> {em.cdm_entity}: AUTO={auto} REVIEW={review} MANUAL={manual}")
    for fm in em.field_mappings:
        print(f"  {fm['source_field']:25s} -> {fm['cdm_field']:25s}  [{fm['band']}]")
