CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.erp_mapping_runs (
    run_id          STRING      NOT NULL DEFAULT uuid(),
    engagement_id   STRING      NOT NULL,
    erp_type        STRING      NOT NULL,
    started_at      TIMESTAMP   NOT NULL,
    completed_at    TIMESTAMP,
    status          STRING      NOT NULL DEFAULT 'running',
    field_count     INT,
    entity_count    INT,
    metadata_json   STRING
)
USING DELTA
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact'   = 'true',
    'erp_auto_mapper.cdm_version'         = '1.0.0'
);
