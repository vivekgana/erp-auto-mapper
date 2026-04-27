"""Unit tests for CDMRegistry — entities, field types, custom registration."""

from typing import Optional

from pydantic import Field, create_model

from erp_auto_mapper.core.cdm.entities import CDMBase
from erp_auto_mapper.core.cdm.registry import CDMRegistry


def test_list_10_entities():
    r = CDMRegistry()
    entities = r.list_entities()
    assert len(entities) == 10
    assert "JournalEntry" in entities
    assert "Account" in entities


def test_get_field_type():
    r = CDMRegistry()
    ft = r.get_field_type("JournalEntry", "company_code")
    assert ft is not None


def test_register_custom_entity():
    r = CDMRegistry()
    FixedAsset = create_model(
        "FixedAsset",
        __base__=CDMBase,
        asset_id=(Optional[str], Field(default=None)),
        book_value=(Optional[float], Field(default=None)),
    )
    r.register_entity("FixedAsset", FixedAsset, version="1")
    assert "FixedAsset" in r.list_entities()
    assert len(r.list_entities()) == 11


def test_get_all_field_names():
    r = CDMRegistry()
    fields = r.get_all_field_names("JournalEntry")
    assert len(fields) > 0
    assert "company_code" in fields or "entry_id" in fields
