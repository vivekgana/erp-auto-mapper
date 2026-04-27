# Databricks notebook source
# MAGIC %md
# MAGIC # Batch Mapping Job
# MAGIC Scheduled job that processes ERP files from a staging volume and writes results to Delta.

# COMMAND ----------

# MAGIC %pip install erp-auto-mapper[all]

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import asyncio
from pathlib import Path
from erp_auto_mapper import ERPMappingOrchestrator, OrchestratorConfig
from erp_auto_mapper.core.extractors.base import EntityMetadata, ERPMetadata, ERPType, FieldMetadata
from erp_auto_mapper.core.ingest.file_reader import FileFormatReader
from erp_auto_mapper.core.ingest.schema_inferrer import SchemaInferrer

# COMMAND ----------

catalog = spark.conf.get("erp_auto_mapper.catalog", "erp_auto_mapper_dev")
schema_name = spark.conf.get("erp_auto_mapper.schema", "mapper")
staging_path = spark.conf.get("erp_auto_mapper.staging_path", "/Volumes/staging/erp_files/")

# COMMAND ----------

reader = FileFormatReader()
inferrer = SchemaInferrer()

# COMMAND ----------

files = list(Path(staging_path).glob("*.csv")) + list(Path(staging_path).glob("*.json"))
print(f"Found {len(files)} files to process")

# COMMAND ----------

results = []
for filepath in files:
    engagement_id = filepath.stem
    print(f"\nProcessing: {filepath.name}")

    read_result = reader.read(filepath)
    inferred_fields = inferrer.infer_fields(read_result.rows)

    entity = EntityMetadata(name=filepath.stem, fields=inferred_fields)
    metadata = ERPMetadata(source=ERPType.SAP, entities=[entity])

    config = OrchestratorConfig(engagement_id=engagement_id)
    orchestrator = ERPMappingOrchestrator(config=config)
    result = asyncio.run(orchestrator.run(metadata))

    for em in result.entity_mappings:
        auto = sum(1 for fm in em.field_mappings if fm["band"] == "auto")
        print(f"  {em.source_entity} -> {em.cdm_entity}: {len(em.field_mappings)} fields ({auto} auto)")

    results.append(result)

# COMMAND ----------

print(f"\nBatch complete. Processed {len(files)} files, {len(results)} results.")
