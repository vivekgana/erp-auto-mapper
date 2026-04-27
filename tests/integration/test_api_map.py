"""Integration tests for POST /v1/map."""

import pytest
from fastapi.testclient import TestClient

from erp_auto_mapper.api.app import create_app
from erp_auto_mapper.api.config import MapperSettings


@pytest.fixture
def client() -> TestClient:
    settings = MapperSettings(auth_disabled=True)
    app = create_app(settings)
    return TestClient(app)


def test_map_sap_success(client: TestClient):
    resp = client.post("/v1/map", json={
        "engagement_id": "test-001",
        "erp_type": "sap",
        "entities": [{
            "name": "BKPF",
            "fields": [
                {"name": "BUKRS", "type": "string", "description": "Company Code"},
                {"name": "BELNR", "type": "string", "description": "Document Number"},
            ],
        }],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["engagement_id"] == "test-001"
    assert len(data["entity_mappings"]) > 0


def test_map_missing_engagement_id(client: TestClient):
    resp = client.post("/v1/map", json={
        "erp_type": "sap",
        "entities": [{"name": "T", "fields": [{"name": "F", "type": "string"}]}],
    })
    assert resp.status_code == 422


def test_map_field_limit(client: TestClient):
    fields = [{"name": f"field_{i}", "type": "string"} for i in range(51)]
    resp = client.post("/v1/map", json={
        "engagement_id": "test-limit",
        "erp_type": "generic",
        "entities": [{"name": "Big", "fields": fields}],
    })
    assert resp.status_code == 400
    assert "Free tier" in resp.json()["detail"]
