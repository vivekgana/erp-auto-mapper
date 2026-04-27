CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.erp_mapping_results (
    result_id       STRING      NOT NULL DEFAULT uuid(),
    run_id          STRING      NOT NULL,
    engagement_id   STRING      NOT NULL,
    source_entity   STRING      NOT NULL,
    cdm_entity      STRING      NOT NULL,
    source_field    STRING      NOT NULL,
    cdm_field       STRING      NOT NULL,
    confidence      DOUBLE      NOT NULL,
    band            STRING      NOT NULL,
    method          STRING,
    source_type     STRING,
    cdm_type        STRING,
    transform_expr  STRING      DEFAULT 'direct',
    rationale       STRING,
    mapped_at       TIMESTAMP   NOT NULL DEFAULT current_timestamp()
)
USING DELTA
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact'   = 'true',
    'erp_auto_mapper.cdm_version'         = '1.0.0'
);
