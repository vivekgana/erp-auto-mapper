"""Tests for Knowledge Assistant skill functions."""

from unittest.mock import patch

from erp_auto_mapper.ka.skills import (
    get_entity_schema,
    list_cdm_entities,
    lookup_alias,
    resolve_entity,
    run_mapping,
)


class TestLookupAlias:
    def test_known_alias_company_code(self):
        result = lookup_alias("company_code")
        assert result["found"] is True
        assert result["cdm_field"] == "company_code"

    def test_known_alias_snake_case(self):
        result = lookup_alias("fiscal_year")
        assert result["found"] is True
        assert result["cdm_field"] == "period"

    def test_unknown_field(self):
        result = lookup_alias("ZZUNKNOWN_CUSTOM_FIELD")
        assert result["found"] is False
        assert result["cdm_field"] == ""

    def test_camel_case_normalized(self):
        result = lookup_alias("DocumentNumber")
        assert result["normalized_as"] == "document_number"

    def test_known_alias_document_number(self):
        result = lookup_alias("document_number")
        assert result["found"] is True
        assert result["cdm_field"] == "entry_id"


class TestResolveEntity:
    def test_known_sap_table(self):
        result = resolve_entity("BKPF")
        assert result["found"] is True
        assert result["cdm_entity"] == "JournalEntry"
        assert result["method"] == "hint"

    def test_known_oracle_table(self):
        result = resolve_entity("GL_JE_LINES")
        assert result["found"] is True
        assert result["cdm_entity"] == "JournalEntry"

    def test_account_table(self):
        result = resolve_entity("SKA1")
        assert result["found"] is True
        assert result["cdm_entity"] == "Account"

    def test_unknown_table_returns_candidates(self):
        result = resolve_entity("ZZRANDOM")
        assert result["found"] is False
        assert isinstance(result["candidates"], list)

    def test_token_overlap_fallback(self):
        result = resolve_entity("Journal_Entry")
        assert result["found"] is True
        assert result["cdm_entity"] == "JournalEntry"


class TestListCdmEntities:
    def test_returns_10_entities(self):
        entities = list_cdm_entities()
        assert len(entities) == 10

    def test_sorted(self):
        entities = list_cdm_entities()
        assert entities == sorted(entities)

    def test_contains_key_entities(self):
        entities = list_cdm_entities()
        for expected in ["JournalEntry", "Account", "Invoice", "Payment"]:
            assert expected in entities


class TestGetEntitySchema:
    def test_journal_entry_has_fields(self):
        result = get_entity_schema("JournalEntry")
        assert result["found"] is True
        assert result["field_count"] > 0
        names = [f["name"] for f in result["fields"]]
        assert "entry_id" in names

    def test_all_fields_have_type(self):
        result = get_entity_schema("Account")
        assert result["found"] is True
        for field in result["fields"]:
            assert field["type"] != ""
            assert field["name"] != ""

    def test_unknown_entity(self):
        result = get_entity_schema("NonExistentEntity")
        assert result["found"] is False
        assert result["field_count"] == 0


class TestRunMapping:
    def test_sap_mapping_returns_results(self):
        result = run_mapping(
            source_fields=[
                {"name": "BUKRS", "type": "string", "description": "Company Code"},
                {"name": "BELNR", "type": "string", "description": "Document Number"},
            ],
            erp_type="sap",
            entity_name="BKPF",
        )
        assert result["cdm_entity"] != ""
        assert len(result["field_mappings"]) == 2
        assert "stats" in result
        assert "avg_confidence" in result["stats"]

    def test_custom_engagement_id(self):
        result = run_mapping(
            source_fields=[{"name": "BUKRS", "type": "string"}],
            erp_type="sap",
            entity_name="BKPF",
            engagement_id="test-123",
        )
        assert result["engagement_id"] == "test-123"

    def test_mapping_has_confidence_bands(self):
        result = run_mapping(
            source_fields=[
                {"name": "BUKRS", "type": "string", "description": "Company Code"},
            ],
            erp_type="sap",
            entity_name="BKPF",
        )
        for fm in result["field_mappings"]:
            assert "band" in fm
            assert fm["band"] in ("auto", "review", "manual")


class TestSearchCdmFields:
    def test_search_with_mocked_index(self):
        mock_results = [
            {
                "doc_id": "cdm_field::JournalEntry::posting_date",
                "doc_type": "cdm_field",
                "entity_name": "JournalEntry",
                "field_name": "posting_date",
                "text": "JournalEntry | posting_date | date",
                "payload": {"field_type": "date"},
                "score": 0.95,
            }
        ]
        with patch("erp_auto_mapper.ka.vector_index.query_index", return_value=mock_results):
            from erp_auto_mapper.ka.skills import search_cdm_fields
            results = search_cdm_fields("posting date")
            assert len(results) == 1
            assert results[0]["field_name"] == "posting_date"

    def test_search_filters_non_cdm_field_docs(self):
        mock_results = [
            {"doc_type": "alias", "entity_name": "", "field_name": "period", "text": "x", "payload": {}, "score": 0.9},
            {"doc_type": "cdm_field", "entity_name": "JournalEntry", "field_name": "period", "text": "y", "payload": {"field_type": "str"}, "score": 0.8},
        ]
        with patch("erp_auto_mapper.ka.vector_index.query_index", return_value=mock_results):
            from erp_auto_mapper.ka.skills import search_cdm_fields
            results = search_cdm_fields("period")
            assert len(results) == 1
            assert results[0]["entity_name"] == "JournalEntry"
