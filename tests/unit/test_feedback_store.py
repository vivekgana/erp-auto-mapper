"""Unit tests for FeedbackStore — boost computation."""

from erp_auto_mapper.core.feedback.store import FeedbackEntry, FeedbackStore


def test_correction_boost():
    store = FeedbackStore()
    store.record_feedback(FeedbackEntry(
        source_field="BUKRS",
        original_cdm_field="entity_id",
        corrected_cdm_field="company_code",
        feedback_type="correction",
        erp_type="sap",
        engagement_id="test",
    ))
    boost = store.compute_boost("sap", "BUKRS", "company_code")
    assert boost > 0.0


def test_no_feedback_zero_boost():
    store = FeedbackStore()
    boost = store.compute_boost("sap", "UNKNOWN", "field")
    assert boost == 0.0


def test_multiple_feedbacks():
    store = FeedbackStore()
    store.record_feedback(FeedbackEntry(
        source_field="A", original_cdm_field="x", corrected_cdm_field="y",
        feedback_type="correction", erp_type="sap",
    ))
    store.record_feedback(FeedbackEntry(
        source_field="B", original_cdm_field="z", corrected_cdm_field="w",
        feedback_type="correction", erp_type="sap",
    ))
    entries = store.get_all_entries()
    assert len(entries) == 2


def test_count():
    store = FeedbackStore()
    assert store.count() == 0
    store.record_feedback(FeedbackEntry(
        source_field="X", original_cdm_field="a", erp_type="sap",
    ))
    assert store.count() == 1
