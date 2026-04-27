"""Unit tests for EmbeddingMappingPass — alias hits, Levenshtein, top_k."""

from erp_auto_mapper.core.cdm.registry import CDMRegistry
from erp_auto_mapper.core.extractors.base import FieldMetadata
from erp_auto_mapper.core.mapper.embedding_pass import EmbeddingMappingPass


def test_alias_match_high_confidence(cdm_registry: CDMRegistry):
    fields = [FieldMetadata(name="company_code", type="string")]
    ep = EmbeddingMappingPass(cdm_registry)
    candidates = ep.map_fields(fields, "JournalEntry")
    cc = [c for c in candidates if c.source_field == "company_code"]
    assert len(cc) > 0
    best = max(cc, key=lambda c: c.score)
    assert best.cdm_field == "company_code"
    assert best.score >= 0.9
    assert best.method == "alias"


def test_description_boost(cdm_registry: CDMRegistry):
    fields = [FieldMetadata(name="BUKRS", type="string", description="Company Code")]
    ep = EmbeddingMappingPass(cdm_registry)
    candidates = ep.map_fields(fields, "JournalEntry")
    bukrs = [c for c in candidates if c.source_field == "BUKRS"]
    assert len(bukrs) > 0
    best = max(bukrs, key=lambda c: c.score)
    assert best.cdm_field == "company_code"


def test_camel_case_normalization(cdm_registry: CDMRegistry):
    fields = [FieldMetadata(name="CompanyCode", type="string")]
    ep = EmbeddingMappingPass(cdm_registry)
    candidates = ep.map_fields(fields, "JournalEntry")
    cc = [c for c in candidates if c.source_field == "CompanyCode"]
    assert any(c.cdm_field == "company_code" for c in cc)


def test_top_k_limiting(cdm_registry: CDMRegistry):
    fields = [FieldMetadata(name="some_field", type="string")]
    ep = EmbeddingMappingPass(cdm_registry, top_k=3)
    candidates = ep.map_fields(fields, "JournalEntry")
    per_source = [c for c in candidates if c.source_field == "some_field"]
    assert len(per_source) <= 3


def test_unknown_field_returns_candidates(cdm_registry: CDMRegistry):
    fields = [FieldMetadata(name="xyzzy_unknown_999", type="string")]
    ep = EmbeddingMappingPass(cdm_registry)
    candidates = ep.map_fields(fields, "JournalEntry")
    assert len(candidates) > 0


def test_empty_fields(cdm_registry: CDMRegistry):
    ep = EmbeddingMappingPass(cdm_registry)
    candidates = ep.map_fields([], "JournalEntry")
    assert candidates == []
