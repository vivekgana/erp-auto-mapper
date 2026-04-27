"""Integration tests for POST /v1/validate."""

import pytest
from fastapi.testclient import TestClient

from erp_auto_mapper.api.app import create_app
from erp_auto_mapper.api.config import MapperSettings


@pytest.fixture
def client() -> TestClient:
    settings = MapperSettings(auth_disabled=True)
    return TestClient(create_app(settings))


def test_validate_success(client: TestClient):
    resp = client.post("/v1/validate", json={
        "engagement_id": "test-val",
        "mappings": [{
            "field_mappings": [
                {"source_field": "BUKRS", "target_field": "company_code", "confidence": 0.95, "source_type": "string", "cdm_type": "string"},
            ]
        }],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "eval_report" in data
    assert data["eval_report"]["aggregate"] >= 0.0


def test_validate_missing_engagement_id(client: TestClient):
    resp = client.post("/v1/validate", json={
        "mappings": [{"field_mappings": []}],
    })
    assert resp.status_code == 422
