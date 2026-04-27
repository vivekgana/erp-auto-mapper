"""Unit tests for TransformationGenerator — SQL codegen."""

from erp_auto_mapper.core.transform.generator import TransformationGenerator


def test_generate_full_returns_output():
    gen = TransformationGenerator()
    mapping = {
        "source_table": "bronze_bkpf",
        "cdm_entity": "JournalEntry",
        "fields": [
            {"source": "BUKRS", "target": "company_code", "transform": "direct"},
            {"source": "BLDAT", "target": "document_date", "transform": "sap_date_to_iso"},
        ],
    }
    result = gen.generate_full(mapping)
    assert result.sql_staging is not None
    assert "BUKRS" in result.sql_staging
    assert result.sql_transform is not None
    assert result.sql_mart is not None


def test_staging_sql():
    gen = TransformationGenerator()
    mapping = {
        "fields": [
            {"source": "BUKRS", "target": "company_code"},
        ],
    }
    sql = gen.generate_staging_sql(mapping, source_table="raw_bkpf")
    assert "BUKRS" in sql
    assert "company_code" in sql
    assert "raw_bkpf" in sql


def test_empty_fields():
    gen = TransformationGenerator()
    mapping = {"source_table": "src", "cdm_entity": "X", "fields": []}
    result = gen.generate_full(mapping)
    assert result.sql_staging is not None
