CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.ka_vector_docs (
    doc_id       STRING NOT NULL,
    doc_type     STRING NOT NULL,
    entity_name  STRING,
    field_name   STRING,
    text         STRING NOT NULL,
    payload_json STRING NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT current_timestamp()
)
USING DELTA
TBLPROPERTIES (
    'delta.enableChangeDataFeed' = 'true',
    'delta.autoOptimize.optimizeWrite' = 'true'
);
