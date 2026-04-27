"""SchemaInferrer — infers field types, nullability, and constraints from sample values."""

from __future__ import annotations

import re
from typing import Any

from erp_auto_mapper.core.extractors.base import FieldMetadata

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SAP_DATS_RE = re.compile(r"^\d{8}$")
_US_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
_INTEGER_RE = re.compile(r"^-?\d+$")
_DECIMAL_RE = re.compile(r"^-?\d+\.\d+$")
_BOOLEAN_VALUES = {"true", "false", "yes", "no", "1", "0", "t", "f", "y", "n"}
_NULL_SENTINELS = {None, "", "null", "NULL", "None", "NONE", "NA", "N/A", "#N/A", "nan", "NaN"}


class SchemaInferrer:
    """Infer FieldMetadata from raw row data."""

    def infer_fields(
        self, rows: list[dict[str, Any]], max_sample: int = 100
    ) -> list[FieldMetadata]:
        if not rows:
            return []

        sample = rows[:max_sample]
        columns = list(rows[0].keys())
        result: list[FieldMetadata] = []

        for col in columns:
            values = [row.get(col) for row in sample]
            non_null = [v for v in values if v not in _NULL_SENTINELS]
            nullable = len(non_null) < len(values)
            inferred_type = self._infer_type(non_null)
            sample_vals = [v for v in non_null[:5] if v is not None]
            max_len = self._detect_max_length(non_null)

            result.append(
                FieldMetadata(
                    name=col,
                    type=inferred_type,
                    nullable=nullable,
                    sample_values=sample_vals,
                    max_length=max_len,
                )
            )

        return result

    def _infer_type(self, values: list[Any]) -> str:
        if not values:
            return "string"

        str_values = [str(v) for v in values]

        if self._all_match_boolean(str_values):
            return "boolean"
        if self._all_match_datetime(str_values):
            return "datetime"
        date_type = self._detect_date_format(str_values)
        if date_type:
            return date_type
        if self._all_match_integer(values):
            return "integer"
        if self._all_match_decimal(values):
            return "decimal"
        return "string"

    @staticmethod
    def _all_match_boolean(values: list[str]) -> bool:
        return all(v.lower() in _BOOLEAN_VALUES for v in values)

    @staticmethod
    def _all_match_integer(values: list[Any]) -> bool:
        for v in values:
            if isinstance(v, bool):
                return False
            if isinstance(v, int):
                continue
            if isinstance(v, str) and _INTEGER_RE.match(v.strip()):
                continue
            return False
        return True

    @staticmethod
    def _all_match_decimal(values: list[Any]) -> bool:
        for v in values:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                continue
            if isinstance(v, str):
                s = v.strip()
                if _DECIMAL_RE.match(s) or _INTEGER_RE.match(s):
                    continue
            return False
        return True

    @staticmethod
    def _detect_date_format(values: list[str]) -> str | None:
        if not values:
            return None
        iso_count = sum(1 for v in values if _ISO_DATE_RE.match(v.strip()))
        sap_count = sum(1 for v in values if _SAP_DATS_RE.match(v.strip()))
        us_count = sum(1 for v in values if _US_DATE_RE.match(v.strip()))
        threshold = len(values) * 0.8

        if iso_count >= threshold:
            return "date"
        if us_count >= threshold:
            return "date"
        if sap_count >= threshold and sap_count > iso_count:
            return "date"
        return None

    @staticmethod
    def _all_match_datetime(values: list[str]) -> bool:
        return all(_DATETIME_RE.match(v.strip()) for v in values)

    @staticmethod
    def _detect_max_length(values: list[Any]) -> int | None:
        if not values:
            return None
        lengths = [len(str(v)) for v in values if v is not None]
        return max(lengths) if lengths else None
