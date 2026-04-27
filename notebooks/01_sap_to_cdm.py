# Databricks notebook source
# MAGIC %md
# MAGIC # SAP -> CDM Full Walkthrough
# MAGIC Demonstrates the complete 3-pass ensemble mapping with eval scoring.

# COMMAND ----------

import asyncio
from erp_auto_mapper import CDMRegistry, ERPMappingOrchestrator, OrchestratorConfig, MappingScorer
from erp_auto_mapper.core.extractors.base import EntityMetadata, ERPMetadata, ERPType, FieldMetadata
from erp_auto_mapper.core.eval.mapping_scorer import MappingInput

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Define SAP Schema

# COMMAND ----------

sap_fields = [
    FieldMetadata(name="BUKRS", type="string", description="Company Code"),
    FieldMetadata(name="BELNR", type="string", description="Document Number"),
    FieldMetadata(name="GJAHR", type="string", description="Fiscal Year"),
    FieldMetadata(name="BLDAT", type="date", description="Document Date"),
    FieldMetadata(name="BUDAT", type="date", description="Posting Date"),
    FieldMetadata(name="WAERS", type="string", description="Currency Key"),
    FieldMetadata(name="MONAT", type="string", description="Fiscal Period"),
    FieldMetadata(name="WRBTR", type="decimal", description="Amount in Doc Currency"),
    FieldMetadata(name="DMBTR", type="decimal", description="Amount in Local Currency"),
    FieldMetadata(name="USNAM", type="string", description="User Name"),
]

metadata = ERPMetadata(
    source=ERPType.SAP,
    entities=[EntityMetadata(name="BKPF", fields=sap_fields)],
)
print(f"Schema: {len(metadata.entities)} entities, {metadata.field_count()} fields")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Run 3-Pass Mapping

# COMMAND ----------

config = OrchestratorConfig(engagement_id="sap-walkthrough")
orchestrator = ERPMappingOrchestrator(config=config)
result = asyncio.run(orchestrator.run(metadata))

# COMMAND ----------

for em in result.entity_mappings:
    print(f"\n{'='*60}")
    print(f"{em.source_entity} -> {em.cdm_entity}")
    print(f"{'='*60}")
    for fm in em.field_mappings:
        print(f"  {fm['source_field']:25s} -> {fm['cdm_field']:25s}  conf={fm['confidence']:.2f}  band={fm['band']:6s}  method={fm.get('method', '')}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Evaluate Quality (per-field scoring)

# COMMAND ----------

scorer = MappingScorer()
cdm = CDMRegistry()

for em in result.entity_mappings:
    print(f"\n{em.source_entity} -> {em.cdm_entity}")
    for fm in em.field_mappings:
        inp = MappingInput(
            source_field=fm["source_field"],
            cdm_field=fm["cdm_field"],
            mapping_confidence=fm["confidence"],
        )
        eval_result = scorer.score(inp)
        print(f"  {fm['source_field']:20s}: aggregate={eval_result.aggregate:.3f}  passed={eval_result.passed}")
