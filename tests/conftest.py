"""Shared test fixtures for erp_auto_mapper."""

from __future__ import annotations

import pytest

from erp_auto_mapper.core.cdm.registry import CDMRegistry
from erp_auto_mapper.core.extractors.base import (
    EntityMetadata,
    ERPMetadata,
    ERPType,
    FieldMetadata,
)


@pytest.fixture
def cdm_registry() -> CDMRegistry:
    return CDMRegistry()


@pytest.fixture
def sap_journal_fields() -> list[FieldMetadata]:
    return [
        FieldMetadata(name="BUKRS", type="string", description="Company Code"),
        FieldMetadata(name="BELNR", type="string", description="Document Number"),
        FieldMetadata(name="GJAHR", type="string", description="Fiscal Year"),
        FieldMetadata(name="BLDAT", type="date", description="Document Date"),
        FieldMetadata(name="BUDAT", type="date", description="Posting Date"),
        FieldMetadata(name="WAERS", type="string", description="Currency Key"),
        FieldMetadata(name="MONAT", type="string", description="Fiscal Period"),
        FieldMetadata(name="WRBTR", type="decimal", description="Amount in Doc Currency"),
        FieldMetadata(name="DMBTR", type="decimal", description="Amount in Local Currency"),
        FieldMetadata(name="USNAM", type="string", description="User Name"),
    ]


@pytest.fixture
def sap_journal_entity(sap_journal_fields: list[FieldMetadata]) -> EntityMetadata:
    return EntityMetadata(name="BKPF", fields=sap_journal_fields)


@pytest.fixture
def sap_metadata(sap_journal_entity: EntityMetadata) -> ERPMetadata:
    return ERPMetadata(source=ERPType.SAP, entities=[sap_journal_entity])


@pytest.fixture
def sap_golden_set() -> list[dict[str, str]]:
    return [
        {"source": "BUKRS", "cdm": "company_code"},
        {"source": "BELNR", "cdm": "entry_id"},
        {"source": "GJAHR", "cdm": "fiscal_year"},
        {"source": "BLDAT", "cdm": "document_date"},
        {"source": "BUDAT", "cdm": "posting_date"},
        {"source": "WAERS", "cdm": "currency_code"},
        {"source": "MONAT", "cdm": "period"},
        {"source": "WRBTR", "cdm": "amount"},
        {"source": "DMBTR", "cdm": "amount_local"},
        {"source": "USNAM", "cdm": "created_by"},
    ]


class MockDeltaClient:
    """In-memory Delta client for testing."""

    def __init__(self) -> None:
        self._tables: dict[str, list[dict]] = {}

    def write_rows(self, table: str, rows: list[dict]) -> int:
        if table not in self._tables:
            self._tables[table] = []
        self._tables[table].extend(rows)
        return len(rows)

    def read_table(self, table: str, limit: int = 1000) -> list[dict]:
        return self._tables.get(table, [])[:limit]

    def execute_sql(self, sql: str) -> list[dict]:
        return []


@pytest.fixture
def mock_delta_client() -> MockDeltaClient:
    return MockDeltaClient()


async def mock_llm(prompt: str) -> str:
    """Mock LLM that returns empty JSON."""
    return "{}"


@pytest.fixture
def mock_llm_callable():
    return mock_llm
