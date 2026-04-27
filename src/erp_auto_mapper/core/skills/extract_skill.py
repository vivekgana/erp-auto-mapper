"""ExtractSkill — multi-source ERP metadata extraction."""

from __future__ import annotations

import logging
from pathlib import Path

from erp_auto_mapper.core.extractors.base import ERPConnectionConfig, ERPMetadata, ERPType
from erp_auto_mapper.core.skills.base import SkillContext, SkillResult

logger = logging.getLogger(__name__)


class ExtractSkill:
    """Extract ERPMetadata from API, files, or pre-built metadata."""

    def __init__(
        self,
        source_type: str = "file",
        erp_type: str = "sap",
        source_files: list[str] | None = None,
        erp_connection: ERPConnectionConfig | None = None,
    ) -> None:
        self._source_type = source_type
        self._erp_type = erp_type
        self._source_files = source_files or []
        self._erp_connection = erp_connection

    @property
    def name(self) -> str:
        return "extract"

    async def execute(self, context: SkillContext) -> SkillResult:
        if context.metadata is not None:
            return SkillResult(
                skill_name=self.name,
                output=context.metadata,
                metrics={"entities": len(context.metadata.entities)},
            )

        erp_type = self._erp_type or context.erp_type
        source_files = self._source_files or context.config.get("source_files", [])

        if self._source_type == "file" and source_files:
            metadata = await self._extract_from_files(source_files, erp_type)
        elif self._source_type == "api" and self._erp_connection:
            metadata = await self._extract_from_api()
        else:
            return SkillResult(
                skill_name=self.name,
                status="failed",
                error="No source configured: provide source_files or erp_connection",
            )

        context.metadata = metadata
        return SkillResult(
            skill_name=self.name,
            output=metadata,
            metrics={
                "entities": len(metadata.entities),
                "fields": metadata.field_count(),
            },
        )

    async def _extract_from_files(
        self, source_files: list[str], erp_type: str
    ) -> ERPMetadata:
        from erp_auto_mapper.core.extractors.file_extractor import FileBasedExtractor

        erp_type_map = {v.value: v for v in ERPType}
        resolved_type = erp_type_map.get(erp_type, ERPType.SAP)

        files: list[str | Path] = list(source_files)
        extractor = FileBasedExtractor(
            source_files=files,
            erp_type=resolved_type,
        )
        result: ERPMetadata = await extractor.extract()
        return result

    async def _extract_from_api(self) -> ERPMetadata:
        from erp_auto_mapper.core.extractors.sap import SAPExtractor
        from erp_auto_mapper.core.extractors.oracle import OracleERPExtractor

        extractor_map: dict[ERPType, type] = {
            ERPType.SAP: SAPExtractor,
            ERPType.ORACLE: OracleERPExtractor,
        }
        if self._erp_connection is None:
            raise ValueError("erp_connection is required for API extraction")

        cls = extractor_map.get(self._erp_connection.erp_type)
        if cls is None:
            raise ValueError(f"No extractor for: {self._erp_connection.erp_type}")

        extractor = cls(self._erp_connection)
        result: ERPMetadata = await extractor.extract()
        return result
