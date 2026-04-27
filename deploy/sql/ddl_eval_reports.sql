CREATE TABLE IF NOT EXISTS ${catalog}.${schema}.erp_eval_reports (
    eval_id                     STRING      NOT NULL DEFAULT uuid(),
    run_id                      STRING      NOT NULL,
    engagement_id               STRING      NOT NULL,
    aggregate                   DOUBLE      NOT NULL,
    semantic_similarity         DOUBLE,
    type_compatibility          DOUBLE,
    value_distribution_overlap  DOUBLE,
    llm_judge_score             DOUBLE,
    business_rule_compliance    DOUBLE,
    golden_set_match            DOUBLE,
    golden_set_precision        DOUBLE,
    golden_set_recall           DOUBLE,
    golden_set_f1               DOUBLE,
    gate_passed                 BOOLEAN     NOT NULL DEFAULT false,
    evaluated_at                TIMESTAMP   NOT NULL DEFAULT current_timestamp(),
    dimensions_json             STRING
)
USING DELTA
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact'   = 'true',
    'erp_auto_mapper.cdm_version'         = '1.0.0'
);
