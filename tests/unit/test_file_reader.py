"""Unit tests for FileFormatReader — CSV, JSON file reading."""

import json
import tempfile
from pathlib import Path

from erp_auto_mapper.core.ingest.file_reader import FileFormatReader


def test_read_csv():
    reader = FileFormatReader()
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        f.write("name,age,city\nAlice,30,NYC\nBob,25,LA\n")
        tmp = Path(f.name)
    try:
        result = reader.read(tmp)
        assert result.row_count == 2
        assert len(result.rows) == 2
        assert result.rows[0]["name"] == "Alice"
    finally:
        tmp.unlink(missing_ok=True)


def test_read_json():
    reader = FileFormatReader()
    data = [{"id": "1", "amount": 100}, {"id": "2", "amount": 200}]
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        json.dump(data, f)
        tmp = Path(f.name)
    try:
        result = reader.read(tmp)
        assert result.row_count == 2
        assert result.rows[0]["id"] == "1"
    finally:
        tmp.unlink(missing_ok=True)


def test_read_csv_empty():
    reader = FileFormatReader()
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        f.write("col1,col2\n")
        tmp = Path(f.name)
    try:
        result = reader.read(tmp)
        assert result.row_count == 0
    finally:
        tmp.unlink(missing_ok=True)
