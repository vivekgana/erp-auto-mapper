"""DeltaSink — writes ERP mapping output to Unity Catalog Delta tables."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from erp_auto_mapper.core.orchestrator import MappingOutput, RunManifest

logger = logging.getLogger(__name__)

_DDL_MAPPING_RUNS = """\
CREATE TABLE IF NOT EXISTS erp_mapping_runs (
    engagement_id STRING,
    erp_type STRING,
    erp_version STRING,
    timestamp STRING,
    entity_count INT,
    field_count INT,
    total_mappings INT,
    auto_count INT,
    review_count INT,
    manual_count INT,
    overall_confidence DOUBLE,
    eval_aggregate DOUBLE,
    duration_seconds DOUBLE,
    created_at TIMESTAMP
) USING DELTA
"""

_DDL_MAPPING_RESULTS = """\
CREATE TABLE IF NOT EXISTS erp_mapping_results (
    engagement_id STRING,
    source_entity STRING,
    cdm_entity STRING,
    source_field STRING,
    cdm_field STRING,
    confidence DOUBLE,
    band STRING,
    transform_expression STRING,
    rationale STRING,
    method STRING,
    embedding_score DOUBLE,
    created_at TIMESTAMP
) USING DELTA
"""

_DDL_EVAL_REPORTS = """\
CREATE TABLE IF NOT EXISTS erp_eval_reports (
    engagement_id STRING,
    aggregate DOUBLE,
    total_fields INT,
    fields_passed INT,
    golden_set_f1 DOUBLE,
    has_regression BOOLEAN,
    report_json STRING,
    created_at TIMESTAMP
) USING DELTA
"""


class DeltaSink:
    """Writes ERP mapping output to Unity Catalog Delta tables."""

    TABLES = ("erp_mapping_runs", "erp_mapping_results", "erp_eval_reports")

    def __init__(self, delta_client: Any) -> None:
        self._delta = delta_client

    async def ensure_tables(self) -> None:
        await self._delta.ensure_table(_DDL_MAPPING_RUNS)
        await self._delta.ensure_table(_DDL_MAPPING_RESULTS)
        await self._delta.ensure_table(_DDL_EVAL_REPORTS)

    async def write(
        self, output: MappingOutput, manifest: RunManifest
    ) -> dict[str, int]:
        now = datetime.now(timezone.utc).isoformat()
        counts: dict[str, int] = {}

        run_row = {
            "engagement_id": manifest.engagement_id,
            "erp_type": manifest.erp_type,
            "erp_version": manifest.erp_version,
            "timestamp": manifest.timestamp,
            "entity_count": manifest.entity_count,
            "field_count": manifest.field_count,
            "total_mappings": manifest.total_mappings,
            "auto_count": manifest.auto_count,
            "review_count": manifest.review_count,
            "manual_count": manifest.manual_count,
            "overall_confidence": manifest.overall_confidence,
            "eval_aggregate": manifest.eval_aggregate,
            "duration_seconds": manifest.duration_seconds,
            "created_at": now,
        }
        counts["erp_mapping_runs"] = await self._delta.write_rows(
            "erp_mapping_runs", [run_row]
        )

        result_rows = self._flatten_results(output, now)
        counts["erp_mapping_results"] = await self._delta.write_rows(
            "erp_mapping_results", result_rows
        )

        eval_row = self._build_eval_row(output, now)
        if eval_row:
            counts["erp_eval_reports"] = await self._delta.write_rows(
                "erp_eval_reports", [eval_row]
            )
        else:
            counts["erp_eval_reports"] = 0

        logger.info(
            "DeltaSink wrote %s rows for engagement %s",
            counts,
            output.engagement_id,
        )
        return counts

    async def read_run(self, engagement_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await self._delta.read_table(
            "erp_mapping_runs",
            where=f"engagement_id = '{engagement_id}'",
        )
        return result

    async def read_results(self, engagement_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await self._delta.read_table(
            "erp_mapping_results",
            where=f"engagement_id = '{engagement_id}'",
        )
        return result

    async def read_eval(self, engagement_id: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = await self._delta.read_table(
            "erp_eval_reports",
            where=f"engagement_id = '{engagement_id}'",
        )
        return result

    @staticmethod
    def _flatten_results(output: MappingOutput, now: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for em in output.entity_mappings:
            for fm in em.field_mappings:
                rows.append(
                    {
                        "engagement_id": output.engagement_id,
                        "source_entity": em.source_entity,
                        "cdm_entity": em.cdm_entity,
                        "source_field": fm.get("source_field", ""),
                        "cdm_field": fm.get("cdm_field", ""),
                        "confidence": fm.get("confidence", 0.0),
                        "band": fm.get("band", ""),
                        "transform_expression": fm.get("transform_expression", ""),
                        "rationale": fm.get("rationale", ""),
                        "method": fm.get("method", ""),
                        "embedding_score": fm.get("embedding_score", 0.0),
                        "created_at": now,
                    }
                )
        return rows

    @staticmethod
    def _build_eval_row(
        output: MappingOutput, now: str
    ) -> dict[str, Any] | None:
        if not output.eval_report:
            return None
        report = output.eval_report
        golden = report.get("golden_set", {})
        regression = report.get("regression", {})
        return {
            "engagement_id": output.engagement_id,
            "aggregate": report.get("aggregate", 0.0),
            "total_fields": report.get("total_fields", 0),
            "fields_passed": report.get("fields_passed", 0),
            "golden_set_f1": golden.get("f1", None),
            "has_regression": regression.get("has_regression", None),
            "report_json": json.dumps(report, default=str),
            "created_at": now,
        }
