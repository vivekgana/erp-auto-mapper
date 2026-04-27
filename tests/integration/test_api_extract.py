"""Integration tests for POST /v1/extract — file upload and schema inference."""

import io

import pytest
from fastapi.testclient import TestClient

from erp_auto_mapper.api.app import create_app
from erp_auto_mapper.api.config import MapperSettings


@pytest.fixture
def client() -> TestClient:
    settings = MapperSettings(auth_disabled=True)
    app = create_app(settings)
    return TestClient(app)


def test_extract_csv(client: TestClient):
    csv_content = "BUKRS,BELNR,BLDAT\n1000,0001,20260101\n2000,0002,20260201\n"
    resp = client.post(
        "/v1/extract",
        files={"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "test.csv"
    assert data["rows"] == 2
    assert len(data["fields"]) == 3
    field_names = {f["name"] for f in data["fields"]}
    assert "BUKRS" in field_names
    assert "BELNR" in field_names


def test_extract_json(client: TestClient):
    json_content = '[{"BUKRS": "1000", "BELNR": "0001"}, {"BUKRS": "2000", "BELNR": "0002"}]'
    resp = client.post(
        "/v1/extract",
        files={"file": ("data.json", io.BytesIO(json_content.encode()), "application/json")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows"] == 2
    assert len(data["fields"]) >= 2


def test_extract_no_file(client: TestClient):
    resp = client.post("/v1/extract")
    assert resp.status_code == 422
