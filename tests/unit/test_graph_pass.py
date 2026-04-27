"""Unit tests for GraphMappingPass — structural boost."""

from erp_auto_mapper.core.extractors.base import EntityMetadata, FieldMetadata, Relationship
from erp_auto_mapper.core.mapper.graph_pass import GraphMappingPass
from erp_auto_mapper.core.mapper.llm_pass import RefinedMapping


def test_structural_boost_with_neighbors():
    mappings = [
        RefinedMapping(source_field="BUKRS", cdm_field="company_code", confidence=0.80, method="embedding"),
        RefinedMapping(source_field="BELNR", cdm_field="entry_id", confidence=0.80, method="embedding"),
        RefinedMapping(source_field="GJAHR", cdm_field="fiscal_year", confidence=0.80, method="embedding"),
    ]
    entities = [
        EntityMetadata(
            name="BKPF",
            fields=[
                FieldMetadata(name="BUKRS", type="string"),
                FieldMetadata(name="BELNR", type="string"),
                FieldMetadata(name="GJAHR", type="string"),
            ],
            relationships=[
                Relationship(source_entity="BKPF", source_field="BUKRS", target_entity="T001", target_field="BUKRS"),
            ],
        )
    ]
    gp = GraphMappingPass()
    boosted = gp.boost_scores(mappings, entities, ["JournalEntry"])
    assert len(boosted) == 3


def test_no_neighbors_no_boost():
    mappings = [
        RefinedMapping(source_field="SOLO", cdm_field="field_x", confidence=0.70, method="embedding"),
    ]
    entities = [EntityMetadata(name="T", fields=[FieldMetadata(name="SOLO", type="string")])]
    gp = GraphMappingPass()
    boosted = gp.boost_scores(mappings, entities, ["JournalEntry"])
    assert len(boosted) == 1


def test_empty_candidates():
    gp = GraphMappingPass()
    boosted = gp.boost_scores([], [], [])
    assert boosted == []
