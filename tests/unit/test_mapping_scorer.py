"""Unit tests for MappingScorer — 6 dimensions, aggregate, pass/fail."""

from erp_auto_mapper.core.eval.mapping_scorer import (
    FieldMapping,
    MappingInput,
    MappingResult,
    MappingScorer,
)


def test_scorer_returns_aggregate_single_input():
    scorer = MappingScorer()
    inp = MappingInput(
        source_field="BUKRS",
        cdm_field="company_code",
        source_type="string",
        cdm_type="string",
        mapping_confidence=0.95,
    )
    result = scorer.score(inp)
    assert 0.0 <= result.aggregate <= 1.0


def test_scorer_with_mapping_result():
    scorer = MappingScorer()
    mr = MappingResult(
        source_entity="BKPF",
        target_entity="JournalEntry",
        field_mappings=[
            FieldMapping(source_field="BUKRS", target_field="company_code", source_type="string", target_type="string", confidence=0.95),
            FieldMapping(source_field="BELNR", target_field="entry_id", source_type="string", target_type="string", confidence=0.90),
        ],
    )
    result = scorer.score(mr)
    assert result.aggregate > 0.0


def test_scorer_with_golden_set_override():
    scorer = MappingScorer(golden_set_score=1.0)
    inp = MappingInput(
        source_field="BUKRS",
        cdm_field="company_code",
        mapping_confidence=0.95,
    )
    result = scorer.score(inp)
    assert result.aggregate > 0.0


def test_scorer_empty_mapping_result():
    scorer = MappingScorer()
    mr = MappingResult(source_entity="X", target_entity="Y", field_mappings=[])
    result = scorer.score(mr)
    assert result.aggregate <= 0.2


def test_per_dimension_keys():
    scorer = MappingScorer()
    inp = MappingInput(
        source_field="X", cdm_field="y", mapping_confidence=0.5
    )
    result = scorer.score(inp)
    expected = {"semantic_similarity", "type_compatibility", "value_distribution_overlap",
                "llm_judge_score", "business_rule_compliance", "golden_set_match"}
    assert expected.issubset(set(result.per_dimension.keys()))
