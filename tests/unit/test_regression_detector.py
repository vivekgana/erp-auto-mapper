"""Unit tests for RegressionDetector — baseline comparison."""

from erp_auto_mapper.core.eval.regression_detector import MappingEvalResult, RegressionDetector


def test_no_regression_within_threshold():
    detector = RegressionDetector()
    baseline = MappingEvalResult(
        aggregate=0.90,
        per_dimension={"semantic_similarity": 0.90, "type_compatibility": 0.90},
    )
    current = MappingEvalResult(
        aggregate=0.88,
        per_dimension={"semantic_similarity": 0.88, "type_compatibility": 0.88},
    )
    result = detector.detect(current, baseline)
    assert not result.has_regression


def test_regression_beyond_threshold():
    detector = RegressionDetector()
    baseline = MappingEvalResult(
        aggregate=0.90,
        per_dimension={"semantic_similarity": 0.90, "type_compatibility": 0.90},
    )
    current = MappingEvalResult(
        aggregate=0.70,
        per_dimension={"semantic_similarity": 0.70, "type_compatibility": 0.70},
    )
    result = detector.detect(current, baseline)
    assert result.has_regression


def test_improvement_no_regression():
    detector = RegressionDetector()
    baseline = MappingEvalResult(
        aggregate=0.80,
        per_dimension={"semantic_similarity": 0.80},
    )
    current = MappingEvalResult(
        aggregate=0.90,
        per_dimension={"semantic_similarity": 0.90},
    )
    result = detector.detect(current, baseline)
    assert not result.has_regression


def test_stored_baseline():
    detector = RegressionDetector()
    baseline = MappingEvalResult(
        aggregate=0.90,
        per_dimension={"semantic_similarity": 0.90},
    )
    detector.store_baseline("v1", baseline)
    assert "v1" in detector.list_baselines()
    assert detector.get_baseline("v1") is not None
