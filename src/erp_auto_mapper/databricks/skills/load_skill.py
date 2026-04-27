"""Delta-aware LoadSkill — writes mapping results to Delta tables."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from erp_auto_mapper.core.skills.base import SkillContext, SkillResult


class DeltaLoadSkill:
    """Loads mapping output into Delta tables via DeltaClient."""

    def __init__(self, delta_client: Any, catalog: str = "erp_auto_mapper_dev", schema: str = "mapper") -> None:
        self._client = delta_client
        self._catalog = catalog
        self._schema = schema

    async def run(self, context: SkillContext) -> SkillResult:
        engagement_id = context.engagement_id
        now = datetime.now(timezone.utc).isoformat()

        run_table = f"{self._catalog}.{self._schema}.erp_mapping_runs"
        self._client.write_rows(run_table, [{
            "engagement_id": engagement_id,
            "erp_type": context.erp_type,
            "started_at": now,
            "status": "completed",
        }])

        results_table = f"{self._catalog}.{self._schema}.erp_mapping_results"
        result_rows = []
        for em in context.entity_mappings:
            em_dict = em if isinstance(em, dict) else em.__dict__
            for fm in em_dict.get("field_mappings", []):
                result_rows.append({
                    "engagement_id": engagement_id,
                    "source_entity": em_dict.get("source_entity", ""),
                    "cdm_entity": em_dict.get("cdm_entity", ""),
                    "source_field": fm.get("source_field", ""),
                    "cdm_field": fm.get("cdm_field", ""),
                    "confidence": str(fm.get("confidence", 0.0)),
                    "band": fm.get("band", "manual"),
                })
        if result_rows:
            self._client.write_rows(results_table, result_rows)

        eval_table = f"{self._catalog}.{self._schema}.erp_eval_reports"
        eval_report = context.eval_report
        if eval_report:
            self._client.write_rows(eval_table, [{
                "engagement_id": engagement_id,
                "aggregate": str(eval_report.get("aggregate", 0.0)),
                "dimensions_json": json.dumps(eval_report.get("per_dimension", {})),
                "evaluated_at": now,
            }])

        return SkillResult(
            skill_name="load",
            status="success",
            output={"tables_written": 3, "result_rows": len(result_rows)},
        )
