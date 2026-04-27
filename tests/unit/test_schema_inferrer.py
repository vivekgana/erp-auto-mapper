"""Unit tests for SchemaInferrer — type detection from sample data."""

from erp_auto_mapper.core.ingest.schema_inferrer import SchemaInferrer


def test_infer_string_types():
    inferrer = SchemaInferrer()
    rows = [{"name": "Alice", "city": "NYC"}, {"name": "Bob", "city": "LA"}]
    fields = inferrer.infer_fields(rows)
    assert len(fields) == 2
    names = {f.name for f in fields}
    assert "name" in names
    assert "city" in names


def test_infer_numeric_types():
    inferrer = SchemaInferrer()
    rows = [{"amount": 100.5, "count": 3}, {"amount": 200.0, "count": 7}]
    fields = inferrer.infer_fields(rows)
    assert len(fields) == 2


def test_infer_empty_rows():
    inferrer = SchemaInferrer()
    fields = inferrer.infer_fields([])
    assert fields == []


def test_infer_mixed_types():
    inferrer = SchemaInferrer()
    rows = [
        {"id": "1", "amount": 100, "active": True, "date": "2026-01-01"},
        {"id": "2", "amount": 200, "active": False, "date": "2026-02-01"},
    ]
    fields = inferrer.infer_fields(rows)
    assert len(fields) == 4
