# Databricks notebook source
# MAGIC %md
# MAGIC # Eval Pipeline Demo
# MAGIC Run 6-dimension quality scoring with golden set validation.

# COMMAND ----------

from erp_auto_mapper import MappingScorer, GoldenSetEvaluator
from erp_auto_mapper.core.eval.mapping_scorer import MappingInput
from erp_auto_mapper.core.eval.business_rule_validator import BusinessRuleValidator

# COMMAND ----------

# MAGIC %md
# MAGIC ## Per-Field Scoring

# COMMAND ----------

test_mappings = [
    {"source_field": "BUKRS", "cdm_field": "company_code", "confidence": 0.95, "source_type": "string", "cdm_type": "string"},
    {"source_field": "BELNR", "cdm_field": "entry_id", "confidence": 0.90, "source_type": "string", "cdm_type": "string"},
    {"source_field": "BLDAT", "cdm_field": "document_date", "confidence": 0.92, "source_type": "date", "cdm_type": "date"},
]

scorer = MappingScorer()

for m in test_mappings:
    inp = MappingInput(
        source_field=m["source_field"],
        cdm_field=m["cdm_field"],
        mapping_confidence=m["confidence"],
        source_type=m.get("source_type", "string"),
        cdm_type=m.get("cdm_type", "string"),
    )
    result = scorer.score(inp)
    print(f"{m['source_field']:10s} -> {m['cdm_field']:15s}  aggregate={result.aggregate:.3f}  passed={result.passed}")
    for dim, val in result.per_dimension.items():
        print(f"  {dim:30s}: {val:.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Golden Set Evaluation

# COMMAND ----------

golden_set = [
    {"source": "BUKRS", "cdm": "company_code"},
    {"source": "BELNR", "cdm": "entry_id"},
    {"source": "BLDAT", "cdm": "document_date"},
]

predicted = [
    {"source": "BUKRS", "cdm": "company_code"},
    {"source": "BELNR", "cdm": "entry_id"},
    {"source": "BLDAT", "cdm": "document_date"},
]

evaluator = GoldenSetEvaluator()
gs_result = evaluator.evaluate(predicted, golden_set)
print(f"Precision: {gs_result.precision:.3f}")
print(f"Recall:    {gs_result.recall:.3f}")
print(f"F1:        {gs_result.f1:.3f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Business Rule Validation

# COMMAND ----------

validator = BusinessRuleValidator()
mapped_data = {
    "rows": [
        {"debit_amount": 1000.00, "credit_amount": 1000.00},
        {"debit_amount": 500.00, "credit_amount": 500.00},
    ]
}
biz_result = validator.validate(mapped_data, "journal_entry")
score = biz_result.rules_passed / biz_result.rules_checked if biz_result.rules_checked > 0 else 0.0
print(f"Business Rule Score: {score:.3f} ({biz_result.rules_passed}/{biz_result.rules_checked} passed)")
for rule in biz_result.details:
    print(f"  {rule.rule_name}: {'PASS' if rule.passed else 'FAIL'} -- {rule.message}")
