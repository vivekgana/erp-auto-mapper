"""Transformation generator — dbt-style SQL models from confirmed ERP mappings."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from erp_auto_mapper.core.extractors.base import ERPMetadata

logger = logging.getLogger(__name__)


class TransformationOutput(BaseModel):
    """Output bundle from the transformation generator."""

    sql_staging: str
    sql_transform: str
    sql_mart: str


class TransformationGenerator:
    """Generates dbt-style SQL models from confirmed ERP-to-CDM mappings."""

    def __init__(self) -> None:
        pass

    def generate_staging_sql(self, mapping: dict[str, Any], source_table: str) -> str:
        """Layer 1 — staging: 1:1 extraction from raw source table."""
        fields = mapping.get("fields", [])
        select_cols: list[str] = []
        for f in fields:
            src = f.get("source", "")
            tgt = f.get("target", src)
            select_cols.append(f"    {src} AS {tgt}")

        cols_sql = ",\n".join(select_cols) if select_cols else "    *"
        return (
            f"-- dbt staging model for {source_table}\n"
            f"SELECT\n"
            f"{cols_sql}\n"
            f"FROM {{{{ source('raw', '{source_table}') }}}}"
        )

    def generate_transform_sql(self, mapping: dict[str, Any]) -> str:
        """Layer 2 — transform: type casting, SAP conversions, lookups."""
        fields = mapping.get("fields", [])
        select_exprs: list[str] = []
        for f in fields:
            src = f.get("source", "")
            tgt = f.get("target", src)
            transform = f.get("transform", "direct")
            if transform == "sap_date_to_iso":
                expr = (
                    f"    CASE WHEN {src} IS NOT NULL AND {src} <> '00000000' "
                    f"THEN TO_DATE(CONCAT(SUBSTR({src},1,4),'-',SUBSTR({src},5,2),'-',SUBSTR({src},7,2)),'yyyy-MM-dd') "
                    f"ELSE NULL END AS {tgt}"
                )
            elif transform == "lookup_currency":
                expr = f"    lkp_currency.description AS {tgt}"
            else:
                expr = f"    {src} AS {tgt}"
            select_exprs.append(expr)

        cols_sql = ",\n".join(select_exprs) if select_exprs else "    *"
        return f"-- dbt transform model\nSELECT\n{cols_sql}\nFROM {{{{ ref('staging') }}}}"

    def generate_mart_sql(self, mapping: dict[str, Any]) -> str:
        """Layer 3 — mart: CDM-conformant final model."""
        cdm_entity = mapping.get("cdm_entity", "unknown")
        fields = mapping.get("fields", [])
        select_exprs: list[str] = []
        for f in fields:
            tgt = f.get("target", f.get("source", ""))
            select_exprs.append(f"    {tgt}")
        select_exprs.append("    CURRENT_TIMESTAMP() AS _loaded_at")

        cols_sql = ",\n".join(select_exprs) if select_exprs else "    *"
        mart_name = cdm_entity.lower() if cdm_entity[0].isupper() else cdm_entity
        return (
            f"-- dbt mart model: {cdm_entity}\n"
            f"SELECT\n{cols_sql}\n"
            f"FROM {{{{ ref('transform_{mart_name}') }}}}"
        )

    def generate_full(self, mapping: dict[str, Any]) -> TransformationOutput:
        """Generate all three SQL layers."""
        source_table = mapping.get("source_table", "source")
        return TransformationOutput(
            sql_staging=self.generate_staging_sql(mapping, source_table),
            sql_transform=self.generate_transform_sql(mapping),
            sql_mart=self.generate_mart_sql(mapping),
        )

    # ------------------------------------------------------------------
    # SAP-specific type conversions
    # ------------------------------------------------------------------

    @staticmethod
    def convert_sap_date(dats: str) -> str | None:
        """Convert SAP DATS (YYYYMMDD) to ISO 8601 date string."""
        if not dats or dats == "00000000" or len(dats) != 8:
            return None
        try:
            year, month, day = int(dats[:4]), int(dats[4:6]), int(dats[6:8])
            dt = datetime(year, month, day)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            return None

    @staticmethod
    def convert_sap_time(tims: str) -> str | None:
        """Convert SAP TIMS (HHMMSS) to HH:MM:SS string."""
        if not tims or len(tims) != 6:
            return None
        try:
            hh, mm, ss = int(tims[:2]), int(tims[2:4]), int(tims[4:6])
            if hh > 23 or mm > 59 or ss > 59:
                return None
            return f"{hh:02d}:{mm:02d}:{ss:02d}"
        except ValueError:
            return None

    @staticmethod
    def convert_numc(numc: str) -> int:
        """Convert SAP NUMC (zero-padded numeric string) to integer."""
        return int(numc)

    @staticmethod
    def compute_metadata_hash(metadata: ERPMetadata) -> str:
        """Compute a deterministic hash of ERP metadata for drift detection."""
        canonical: list[dict[str, Any]] = []
        for entity in sorted(metadata.entities, key=lambda e: e.name):
            fields_data = []
            for f in sorted(entity.fields, key=lambda fld: fld.name):
                fields_data.append({
                    "name": f.name,
                    "type": f.type,
                    "nullable": f.nullable,
                    "is_key": f.is_key,
                })
            canonical.append({
                "entity": entity.name,
                "fields": fields_data,
            })
        raw = json.dumps(canonical, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()
