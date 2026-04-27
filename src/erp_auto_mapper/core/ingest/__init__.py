"""ERP data ingestion — multi-format file reading and schema inference."""

from erp_auto_mapper.core.ingest.file_reader import FileFormatReader, FileReadResult
from erp_auto_mapper.core.ingest.schema_inferrer import SchemaInferrer

__all__ = [
    "FileFormatReader",
    "FileReadResult",
    "SchemaInferrer",
]
