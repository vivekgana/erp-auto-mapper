"""LoadExecuteSkill — execute generated ETL on the target platform."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from erp_auto_mapper.core.skills.base import SkillContext, SkillResult

logger = logging.getLogger(__name__)


class LoadResult(BaseModel):
    """Result from loading data to a platform."""

    platform: str = ""
    tables_written: list[str] = Field(default_factory=list)
    rows_written: int = 0
    artifacts: dict[str, str] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class LoadExecuteSkill:
    """Execute generated ETL code and persist results."""

    def __init__(
        self,
        platform: str = "databricks",
        delta_client: Any = None,
        output_dir: str = "output",
    ) -> None:
        self._platform = platform
        self._delta_client = delta_client
        self._output_dir = output_dir

    @property
    def name(self) -> str:
        return "load_execute"

    async def execute(self, context: SkillContext) -> SkillResult:
        load_result = LoadResult(platform=self._platform)

        self._persist_to_disk(context, load_result)

        if self._delta_client and context.entity_mappings:
            await self._write_to_delta(context, load_result)

        if (
            self._delta_client
            and context.config.get("bronze_ingest")
            and context.config.get("source_files")
        ):
            await self._bronze_ingest(context, load_result)

        context.load_result = load_result

        return SkillResult(
            skill_name=self.name,
            output=load_result,
            metrics={
                "tables_written": len(load_result.tables_written),
                "rows_written": load_result.rows_written,
                "errors": len(load_result.errors),
            },
        )

    def _persist_to_disk(self, context: SkillContext, result: LoadResult) -> None:
        base = Path(self._output_dir) / context.engagement_id
        sql_dir = base / "sql"
        sql_dir.mkdir(parents=True, exist_ok=True)

        sql = context.config.get("sql", {})
        for layer in ("staging", "transform", "mart"):
            content = sql.get(layer, "")
            if content:
                path = sql_dir / f"{layer}.sql"
                path.write_text(content, encoding="utf-8")
                result.artifacts[f"sql_{layer}"] = str(path)

        if context.generated_code:
            code_path = base / f"platform_code{context.generated_code.file_extension}"
            code_path.write_text(context.generated_code.code, encoding="utf-8")
            result.artifacts["platform_code"] = str(code_path)

        if context.eval_report:
            eval_path = base / "eval_report.json"
            eval_path.write_text(
                json.dumps(context.eval_report, indent=2, default=str),
                encoding="utf-8",
            )
            result.artifacts["eval_report"] = str(eval_path)

    async def _write_to_delta(
        self, context: SkillContext, result: LoadResult
    ) -> None:
        from erp_auto_mapper.core.delta_sink import DeltaSink
        from erp_auto_mapper.core.orchestrator import MappingOutput, RunManifest

        mapping_output = MappingOutput(
            engagement_id=context.engagement_id,
            erp_type=context.erp_type,
            entity_mappings=context.entity_mappings,
            eval_report=context.eval_report or None,
        )
        manifest = RunManifest(
            engagement_id=context.engagement_id,
            erp_type=context.erp_type,
        )

        sink = DeltaSink(self._delta_client)
        await sink.ensure_tables()
        await sink.write(mapping_output, manifest)
        result.tables_written.append("erp_mapping_results")

    async def _bronze_ingest(
        self, context: SkillContext, result: LoadResult
    ) -> None:
        from erp_auto_mapper.core.ingest.bronze_writer import BronzeWriter

        writer = BronzeWriter(self._delta_client)
        source_files = context.config.get("source_files", [])
        for fp in source_files:
            ingest_result = await writer.ingest_file(fp)
            result.tables_written.append(ingest_result.table_name)
            result.rows_written += ingest_result.row_count
