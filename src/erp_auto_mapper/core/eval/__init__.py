"""Auto-Eval system — first-in-industry mapping quality evaluation for ERP-to-CDM."""

from erp_auto_mapper.core.eval.mapping_scorer import MappingEvalResult, MappingScorer
from erp_auto_mapper.core.eval.business_rule_validator import BusinessRuleResult, BusinessRuleValidator
from erp_auto_mapper.core.eval.golden_set_evaluator import GoldenSetEvaluator, GoldenSetResult
from erp_auto_mapper.core.eval.llm_judge import JudgeResult, MappingLLMJudge
from erp_auto_mapper.core.eval.regression_detector import RegressionDetector, RegressionResult
from erp_auto_mapper.core.eval.benchmark_comparator import BenchmarkComparator, BenchmarkResult

__all__ = [
    "MappingScorer",
    "MappingEvalResult",
    "BusinessRuleValidator",
    "BusinessRuleResult",
    "GoldenSetEvaluator",
    "GoldenSetResult",
    "MappingLLMJudge",
    "JudgeResult",
    "RegressionDetector",
    "RegressionResult",
    "BenchmarkComparator",
    "BenchmarkResult",
]
