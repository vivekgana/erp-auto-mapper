"""Integration tests for OAuth2 authentication middleware."""

import pytest
from fastapi.testclient import TestClient

from erp_auto_mapper.api.app import create_app
from erp_auto_mapper.api.config import MapperSettings


@pytest.fixture
def auth_disabled_client() -> TestClient:
    settings = MapperSettings(auth_disabled=True)
    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def auth_enabled_client() -> TestClient:
    settings = MapperSettings(auth_disabled=False, auth_jwks_url="https://invalid.example.com/.well-known/jwks.json")
    app = create_app(settings)
    return TestClient(app)


def test_noop_auth_allows_requests(auth_disabled_client: TestClient):
    resp = auth_disabled_client.get("/v1/cdm/entities")
    assert resp.status_code == 200


def test_noop_auth_no_header_needed(auth_disabled_client: TestClient):
    resp = auth_disabled_client.post("/v1/map", json={
        "engagement_id": "auth-test",
        "erp_type": "sap",
        "entities": [{"name": "T", "fields": [{"name": "F", "type": "string"}]}],
    })
    assert resp.status_code == 200


def test_auth_enabled_rejects_missing_token(auth_enabled_client: TestClient):
    resp = auth_enabled_client.get("/v1/cdm/entities")
    assert resp.status_code == 401
    assert "authorization" in resp.json()["detail"].lower() or "missing" in resp.json()["detail"].lower()


def test_auth_enabled_rejects_bad_token(auth_enabled_client: TestClient):
    resp = auth_enabled_client.get(
        "/v1/cdm/entities",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code in (401, 503)


def test_health_endpoint_no_auth(auth_enabled_client: TestClient):
    resp = auth_enabled_client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
