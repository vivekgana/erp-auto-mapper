"""Unit tests for GoldenSetEvaluator — precision/recall/F1."""

from erp_auto_mapper.core.eval.golden_set_evaluator import GoldenSetEvaluator


def test_perfect_match():
    golden = [
        {"source": "BUKRS", "cdm": "company_code"},
        {"source": "BELNR", "cdm": "entry_id"},
    ]
    predicted = [
        {"source": "BUKRS", "cdm": "company_code"},
        {"source": "BELNR", "cdm": "entry_id"},
    ]
    evaluator = GoldenSetEvaluator()
    result = evaluator.evaluate(predicted, golden)
    assert result.f1 == 1.0
    assert result.precision == 1.0
    assert result.recall == 1.0


def test_no_matches():
    golden = [{"source": "BUKRS", "cdm": "company_code"}]
    predicted = [{"source": "BUKRS", "cdm": "wrong_field"}]
    evaluator = GoldenSetEvaluator()
    result = evaluator.evaluate(predicted, golden)
    assert result.f1 == 0.0


def test_partial_match():
    golden = [
        {"source": "BUKRS", "cdm": "company_code"},
        {"source": "BELNR", "cdm": "entry_id"},
    ]
    predicted = [
        {"source": "BUKRS", "cdm": "company_code"},
        {"source": "BELNR", "cdm": "wrong"},
    ]
    evaluator = GoldenSetEvaluator()
    result = evaluator.evaluate(predicted, golden)
    assert 0.0 < result.f1 < 1.0
    assert result.precision == 0.5


def test_empty_golden_set():
    evaluator = GoldenSetEvaluator()
    result = evaluator.evaluate([{"source": "X", "cdm": "y"}], [])
    assert result.f1 == 0.0
