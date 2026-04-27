"""InferSchemaSkill — type inference from raw data or file paths."""

from __future__ import annotations

import logging
from pathlib import Path

from erp_auto_mapper.core.extractors.base import FieldMetadata
from erp_auto_mapper.core.ingest.schema_inferrer import SchemaInferrer
from erp_auto_mapper.core.skills.base import SkillContext, SkillResult

logger = logging.getLogger(__name__)


class InferSchemaSkill:
    """Infer field types, nullability, and constraints from raw data."""

    def __init__(self, max_sample: int = 100) -> None:
        self._inferrer = SchemaInferrer()
        self._max_sample = max_sample

    @property
    def name(self) -> str:
        return "infer_schema"

    async def execute(self, context: SkillContext) -> SkillResult:
        rows = context.config.get("raw_rows")
        source_files = context.config.get("source_files")

        if rows:
            fields = self._inferrer.infer_fields(rows, max_sample=self._max_sample)
        elif source_files:
            fields = await self._infer_from_files(source_files)
        elif context.metadata is not None:
            total_fields = sum(
                len(e.fields) for e in context.metadata.entities
            )
            return SkillResult(
                skill_name=self.name,
                output=context.metadata,
                metrics={"fields_inferred": total_fields},
            )
        else:
            return SkillResult(
                skill_name=self.name,
                status="failed",
                error="No data to infer schema from: provide raw_rows or source_files in config",
            )

        context.config["inferred_fields"] = fields
        return SkillResult(
            skill_name=self.name,
            output=fields,
            metrics={"fields_inferred": len(fields)},
        )

    async def _infer_from_files(self, source_files: list[str]) -> list[FieldMetadata]:
        from erp_auto_mapper.core.ingest.file_reader import FileFormatReader

        reader = FileFormatReader()
        all_fields: list[FieldMetadata] = []
        for fp in source_files:
            result = reader.read(Path(fp))
            all_fields.extend(result.inferred_fields)
        return all_fields
