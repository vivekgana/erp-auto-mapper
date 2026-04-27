"""Unit tests for MappingEnsemble — confidence band thresholds."""

from erp_auto_mapper.core.mapper.ensemble import ConfidenceBand, MappingEnsemble, MappingResult


def test_auto_band_at_085():
    assert MappingResult.classify_confidence(0.85) == ConfidenceBand.AUTO


def test_auto_band_above_085():
    assert MappingResult.classify_confidence(0.95) == ConfidenceBand.AUTO


def test_review_band_at_050():
    assert MappingResult.classify_confidence(0.50) == ConfidenceBand.REVIEW


def test_review_band_at_084():
    assert MappingResult.classify_confidence(0.84) == ConfidenceBand.REVIEW


def test_manual_band_below_050():
    assert MappingResult.classify_confidence(0.49) == ConfidenceBand.MANUAL


def test_manual_band_zero():
    assert MappingResult.classify_confidence(0.0) == ConfidenceBand.MANUAL


def test_ensemble_weighted_score():
    ensemble = MappingEnsemble()
    score = ensemble._compute_weighted_score(
        string_sim=0.9, semantic_sim=0.9, type_match=1.0, sample_overlap=0.8, structural=0.5
    )
    assert 0.0 < score <= 1.0
