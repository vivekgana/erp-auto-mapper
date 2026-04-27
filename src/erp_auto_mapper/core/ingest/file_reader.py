"""FileFormatReader — reads ERP data files in 8 widely-used formats."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from collections.abc import Callable
from typing import Any
from xml.etree import ElementTree as ET

from pydantic import BaseModel, Field

from erp_auto_mapper.core.extractors.base import FieldMetadata
from erp_auto_mapper.core.ingest.schema_inferrer import SchemaInferrer

logger = logging.getLogger(__name__)

_EXTENSION_MAP: dict[str, str] = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".parquet": "parquet",
    ".xml": "xml",
    ".xlsx": "excel",
    ".xls": "excel",
    ".avro": "avro",
    ".txt": "fixed_width",
    ".dat": "fixed_width",
}


class FileReadResult(BaseModel):
    """Result from reading a raw file."""

    rows: list[dict[str, Any]] = Field(default_factory=list)
    column_names: list[str] = Field(default_factory=list)
    row_count: int = 0
    source_format: str = ""
    source_path: str = ""
    inferred_fields: list[FieldMetadata] = Field(default_factory=list)


class FileFormatReader:
    """Reads ERP data files in any supported format with auto-detection."""

    SUPPORTED_FORMATS = _EXTENSION_MAP

    def __init__(self) -> None:
        self._inferrer = SchemaInferrer()

    def read(
        self,
        path: str | Path,
        format_hint: str | None = None,
        **kwargs: Any,
    ) -> FileReadResult:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        fmt = format_hint or _EXTENSION_MAP.get(path.suffix.lower())
        if fmt is None:
            raise ValueError(
                f"Unsupported file format: {path.suffix}. "
                f"Supported: {', '.join(sorted(_EXTENSION_MAP.keys()))}"
            )

        reader_map: dict[str, Callable[..., FileReadResult]] = {
            "csv": self.read_csv,
            "tsv": lambda p, **kw: self.read_csv(p, delimiter="\t", **kw),
            "json": self.read_json,
            "jsonl": self.read_jsonl,
            "parquet": self.read_parquet,
            "xml": self.read_xml,
            "excel": self.read_excel,
            "fixed_width": self.read_fixed_width,
            "avro": self.read_avro,
        }

        reader = reader_map.get(fmt)
        if reader is None:
            raise ValueError(f"No reader for format: {fmt}")
        return reader(path, **kwargs)

    def read_csv(
        self,
        path: str | Path,
        delimiter: str = ",",
        encoding: str = "utf-8",
        **_: Any,
    ) -> FileReadResult:
        path = Path(path)
        with open(path, newline="", encoding=encoding) as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = list(reader)
            columns = reader.fieldnames or []

        fields = self._inferrer.infer_fields(rows)
        return FileReadResult(
            rows=rows,
            column_names=list(columns),
            row_count=len(rows),
            source_format="csv" if delimiter == "," else "tsv",
            source_path=str(path),
            inferred_fields=fields,
        )

    def read_json(self, path: str | Path, **_: Any) -> FileReadResult:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError(f"JSON must be an array or object, got {type(data).__name__}")

        columns = list(data[0].keys()) if data else []
        fields = self._inferrer.infer_fields(data)
        return FileReadResult(
            rows=data,
            column_names=columns,
            row_count=len(data),
            source_format="json",
            source_path=str(path),
            inferred_fields=fields,
        )

    def read_jsonl(self, path: str | Path, **_: Any) -> FileReadResult:
        path = Path(path)
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))

        columns = list(rows[0].keys()) if rows else []
        fields = self._inferrer.infer_fields(rows)
        return FileReadResult(
            rows=rows,
            column_names=columns,
            row_count=len(rows),
            source_format="jsonl",
            source_path=str(path),
            inferred_fields=fields,
        )

    def read_xml(
        self,
        path: str | Path,
        row_tag: str | None = None,
        **_: Any,
    ) -> FileReadResult:
        path = Path(path)
        tree = ET.parse(path)
        root = tree.getroot()

        if row_tag is None:
            row_tag = self._detect_xml_row_tag(root)

        rows: list[dict[str, Any]] = []
        for elem in root.iter(row_tag):
            row: dict[str, Any] = {}
            for child in elem:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                row[tag] = child.text
            if elem.attrib:
                row.update(elem.attrib)
            if row:
                rows.append(row)

        columns = list(rows[0].keys()) if rows else []
        fields = self._inferrer.infer_fields(rows)
        return FileReadResult(
            rows=rows,
            column_names=columns,
            row_count=len(rows),
            source_format="xml",
            source_path=str(path),
            inferred_fields=fields,
        )

    def read_parquet(self, path: str | Path, **_: Any) -> FileReadResult:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            raise ImportError(
                "pyarrow is required to read Parquet files. "
                "Install with: pip install pyarrow"
            )

        path = Path(path)
        table = pq.read_table(path)
        rows = table.to_pydict()
        n = table.num_rows
        columns = table.column_names
        row_list = [{col: rows[col][i] for col in columns} for i in range(n)]

        fields = self._inferrer.infer_fields(row_list)
        return FileReadResult(
            rows=row_list,
            column_names=columns,
            row_count=n,
            source_format="parquet",
            source_path=str(path),
            inferred_fields=fields,
        )

    def read_excel(
        self,
        path: str | Path,
        sheet: str | int = 0,
        **_: Any,
    ) -> FileReadResult:
        try:
            import openpyxl
        except ImportError:
            raise ImportError(
                "openpyxl is required to read Excel files. "
                "Install with: pip install openpyxl"
            )

        path = Path(path)
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        if isinstance(sheet, int):
            ws = wb.worksheets[sheet]
        else:
            ws = wb[sheet]

        data = list(ws.iter_rows(values_only=True))
        wb.close()

        if not data:
            return FileReadResult(
                source_format="excel", source_path=str(path)
            )

        headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(data[0])]
        rows = [dict(zip(headers, row)) for row in data[1:]]

        fields = self._inferrer.infer_fields(rows)
        return FileReadResult(
            rows=rows,
            column_names=headers,
            row_count=len(rows),
            source_format="excel",
            source_path=str(path),
            inferred_fields=fields,
        )

    def read_fixed_width(
        self,
        path: str | Path,
        col_specs: list[tuple[str, int, int]] | None = None,
        **_: Any,
    ) -> FileReadResult:
        if not col_specs:
            raise ValueError(
                "col_specs is required for fixed-width files: "
                "list of (column_name, start_pos, end_pos)"
            )

        path = Path(path)
        lines = path.read_text(encoding="utf-8").splitlines()
        rows: list[dict[str, Any]] = []

        for line in lines:
            if not line.strip():
                continue
            row: dict[str, Any] = {}
            for name, start, end in col_specs:
                row[name] = line[start:end].strip()
            rows.append(row)

        columns = [spec[0] for spec in col_specs]
        fields = self._inferrer.infer_fields(rows)
        return FileReadResult(
            rows=rows,
            column_names=columns,
            row_count=len(rows),
            source_format="fixed_width",
            source_path=str(path),
            inferred_fields=fields,
        )

    def read_avro(self, path: str | Path, **_: Any) -> FileReadResult:
        try:
            import fastavro
        except ImportError:
            raise ImportError(
                "fastavro is required to read AVRO files. "
                "Install with: pip install fastavro"
            )

        path = Path(path)
        with open(path, "rb") as f:
            reader = fastavro.reader(f)
            rows = list(reader)

        columns = list(rows[0].keys()) if rows else []
        fields = self._inferrer.infer_fields(rows)
        return FileReadResult(
            rows=rows,
            column_names=columns,
            row_count=len(rows),
            source_format="avro",
            source_path=str(path),
            inferred_fields=fields,
        )

    @staticmethod
    def _detect_xml_row_tag(root: ET.Element) -> str:
        tag_counts: dict[str, int] = {}
        for child in root:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if not tag_counts:
            raise ValueError("XML document has no child elements under root")
        return max(tag_counts, key=tag_counts.get)  # type: ignore[arg-type]
