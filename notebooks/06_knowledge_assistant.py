# Databricks notebook source
# MAGIC %md
# MAGIC # ERP Auto Mapper — Knowledge Assistant
# MAGIC
# MAGIC This notebook sets up and demonstrates the Knowledge Assistant (KA) — a conversational
# MAGIC AI agent that can answer questions about ERP-to-CDM mappings using 7 skill functions.
# MAGIC
# MAGIC **Sections:**
# MAGIC 1. Install dependencies
# MAGIC 2. Setup Vector Search index (one-time)
# MAGIC 3. Log agent to MLflow
# MAGIC 4. Demo: use skills directly
# MAGIC 5. Demo: conversational agent

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Install Dependencies

# COMMAND ----------

# MAGIC %pip install erp-auto-mapper[databricks] mlflow>=2.14.0
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Configuration

# COMMAND ----------

dbutils.widgets.text("catalog", "erp_auto_mapper_dev", "Unity Catalog")
dbutils.widgets.text("schema", "mapper", "Schema")
dbutils.widgets.text("vs_endpoint", "erp-auto-mapper-vs", "VS Endpoint")

catalog = dbutils.widgets.get("catalog")
schema_name = dbutils.widgets.get("schema")
vs_endpoint = dbutils.widgets.get("vs_endpoint")

from erp_auto_mapper.ka import KAConfig

config = KAConfig(
    catalog=catalog,
    schema_name=schema_name,
    vs_endpoint_name=vs_endpoint,
)
print(f"Config: catalog={config.catalog}, schema={config.schema_name}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Setup Vector Search Index (One-Time)
# MAGIC
# MAGIC This creates the `ka_vector_docs` Delta table with ~470 documents (CDM fields,
# MAGIC alias entries, entity hints) and a Delta Sync Vector Search index.

# COMMAND ----------

from erp_auto_mapper.ka import build_docs, setup_index

docs = build_docs()
print(f"Generated {len(docs)} documents:")
print(f"  CDM fields:    {sum(1 for d in docs if d['doc_type'] == 'cdm_field')}")
print(f"  Alias entries: {sum(1 for d in docs if d['doc_type'] == 'alias')}")
print(f"  Entity hints:  {sum(1 for d in docs if d['doc_type'] == 'entity_hint')}")

# COMMAND ----------

# Uncomment to create/refresh the VS index (requires VS endpoint to exist):
# setup_index(spark, config, overwrite=True)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Demo: Use Skills Directly
# MAGIC
# MAGIC Each skill is a plain Python function — no agent loop required.

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4a. List all CDM entities

# COMMAND ----------

from erp_auto_mapper.ka import list_cdm_entities
entities = list_cdm_entities()
print(f"{len(entities)} CDM entities: {', '.join(entities)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4b. Get schema for JournalEntry

# COMMAND ----------

from erp_auto_mapper.ka import get_entity_schema
schema = get_entity_schema("JournalEntry")
print(f"JournalEntry has {schema['field_count']} fields:")
for f in schema["fields"]:
    print(f"  {f['name']:25s}  {f['type']:30s}  {f['description']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4c. Look up an ERP field alias

# COMMAND ----------

from erp_auto_mapper.ka import lookup_alias

for field in ["BUKRS", "BELNR", "posting_date", "fiscal_year", "UnknownField"]:
    result = lookup_alias(field)
    status = f"-> {result['cdm_field']}" if result["found"] else "(no alias)"
    print(f"  {field:20s} {status}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4d. Resolve ERP table → CDM entity

# COMMAND ----------

from erp_auto_mapper.ka import resolve_entity

for table in ["BKPF", "GL_JOURNALS", "SKA1", "LFA1", "SomeRandomTable"]:
    result = resolve_entity(table)
    if result["found"]:
        print(f"  {table:20s} -> {result['cdm_entity']} ({result['method']}, score={result['score']:.2f})")
    else:
        print(f"  {table:20s} -> NOT FOUND, candidates: {result['candidates'][:3]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4e. Run a full mapping

# COMMAND ----------

from erp_auto_mapper.ka import run_mapping

result = run_mapping(
    source_fields=[
        {"name": "BUKRS", "type": "string", "description": "Company Code"},
        {"name": "BELNR", "type": "string", "description": "Document Number"},
        {"name": "BLDAT", "type": "date", "description": "Document Date"},
        {"name": "BUDAT", "type": "date", "description": "Posting Date"},
        {"name": "WAERS", "type": "string", "description": "Currency"},
    ],
    erp_type="sap",
    entity_name="BKPF",
)

print(f"Mapped to: {result['cdm_entity']}")
print(f"Stats: {result['stats']}")
print()
for fm in result["field_mappings"]:
    print(f"  {fm['source_field']:20s} -> {fm['cdm_field']:20s}  ({fm['confidence']:.2f} {fm['band']})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Log Agent to MLflow
# MAGIC
# MAGIC Register the Knowledge Assistant as an MLflow model for Model Serving deployment.

# COMMAND ----------

from erp_auto_mapper.ka import log_agent
import mlflow

mlflow.set_experiment(f"/Shared/erp-auto-mapper/ka-{catalog}")
model_uri = log_agent(config=config, registered_model_name=f"{catalog}.{schema_name}.erp_ka_agent")
print(f"Agent registered: {model_uri}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Test the Logged Agent

# COMMAND ----------

from erp_auto_mapper.ka import ERPKnowledgeAssistant

agent = ERPKnowledgeAssistant(config=config)

# Direct tool call
result = agent.call_tool("get_entity_schema", {"entity_name": "Invoice"})
print(f"Invoice entity: {result['field_count']} fields")

# Alias lookup
result = agent.call_tool("lookup_alias", {"source_field": "vendor_name"})
print(f"vendor_name alias: {result}")

# Entity resolution
result = agent.call_tool("resolve_entity", {"erp_table_name": "BSEG"})
print(f"BSEG -> {result['cdm_entity']} ({result['method']})")
