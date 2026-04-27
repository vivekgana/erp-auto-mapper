"""Integration tests for CDM endpoints."""

import pytest
from fastapi.testclient import TestClient

from erp_auto_mapper.api.app import create_app
from erp_auto_mapper.api.config import MapperSettings


@pytest.fixture
def client() -> TestClient:
    settings = MapperSettings(auth_disabled=True)
    return TestClient(create_app(settings))


def test_list_entities(client: TestClient):
    resp = client.get("/v1/cdm/entities")
    assert resp.status_code == 200
    entities = resp.json()
    assert len(entities) >= 10
    names = [e["name"] for e in entities]
    assert "JournalEntry" in names


def test_register_custom_entity(client: TestClient):
    resp = client.post("/v1/cdm/register", json={
        "entity_name": "FixedAsset",
        "cdm_version": "1.1.0",
        "fields": [
            {"name": "asset_id", "type": "string"},
            {"name": "book_value", "type": "decimal"},
        ],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["entity_name"] == "FixedAsset"
    assert data["field_count"] == 2
