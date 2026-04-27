"""Integration tests for DeltaSink with MockDeltaClient."""


from tests.conftest import MockDeltaClient
from erp_auto_mapper.databricks.bronze_writer import BronzeWriter


def test_bronze_writer_writes_rows(mock_delta_client: MockDeltaClient):
    writer = BronzeWriter(mock_delta_client, catalog="test", schema="test")
    result = writer.write(
        table_suffix="journal",
        records=[{"field1": "val1"}, {"field2": "val2"}],
        source_metadata={"erp": "sap"},
    )
    assert result.rows_written == 2
    assert "test.test.bronze_journal" == result.table_name


def test_bronze_writer_empty_records(mock_delta_client: MockDeltaClient):
    writer = BronzeWriter(mock_delta_client, catalog="test", schema="test")
    result = writer.write("empty", records=[])
    assert result.rows_written == 0


def test_mock_delta_read_after_write(mock_delta_client: MockDeltaClient):
    mock_delta_client.write_rows("t1", [{"a": 1}, {"b": 2}])
    rows = mock_delta_client.read_table("t1")
    assert len(rows) == 2
