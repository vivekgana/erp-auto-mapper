"""Integration tests for rate limiting."""

import pytest
from fastapi.testclient import TestClient

from erp_auto_mapper.api.app import create_app
from erp_auto_mapper.api.config import MapperSettings


@pytest.fixture
def client() -> TestClient:
    settings = MapperSettings(auth_disabled=True, rate_limit_requests_per_day=5)
    return TestClient(create_app(settings))


def test_rate_limit_enforced(client: TestClient):
    payload = {
        "engagement_id": "rate-test",
        "erp_type": "sap",
        "entities": [{"name": "T", "fields": [{"name": "F", "type": "string"}]}],
    }
    for i in range(5):
        resp = client.post("/v1/map", json=payload)
        assert resp.status_code == 200, f"Request {i+1} failed"

    resp = client.post("/v1/map", json=payload)
    assert resp.status_code == 429
    assert "Rate limit" in resp.json()["detail"]


def test_field_count_50_ok():
    settings = MapperSettings(auth_disabled=True)
    client = TestClient(create_app(settings))
    fields = [{"name": f"f_{i}", "type": "string"} for i in range(50)]
    resp = client.post("/v1/map", json={
        "engagement_id": "field-50",
        "entities": [{"name": "E", "fields": fields}],
    })
    assert resp.status_code == 200


def test_field_count_51_rejected():
    settings = MapperSettings(auth_disabled=True)
    client = TestClient(create_app(settings))
    fields = [{"name": f"f_{i}", "type": "string"} for i in range(51)]
    resp = client.post("/v1/map", json={
        "engagement_id": "field-51",
        "entities": [{"name": "E", "fields": fields}],
    })
    assert resp.status_code == 400
