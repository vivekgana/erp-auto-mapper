"""FileBasedExtractor — extract ERPMetadata from local files instead of live ERP APIs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from erp_auto_mapper.core.extractors.base import (
    BaseERPExtractor,
    EntityMetadata,
    ERPConnectionConfig,
    ERPMetadata,
    ERPType,
    FieldMetadata,
)
from erp_auto_mapper.core.ingest.file_reader import FileFormatReader

logger = logging.getLogger(__name__)


class FileBasedExtractor(BaseERPExtractor):
    """Extract ERPMetadata from local files — one entity per file."""

    def __init__(
        self,
        source_files: list[str | Path],
        erp_type: ERPType = ERPType.SAP,
        erp_version: str = "",
        format_hints: dict[str, str] | None = None,
        reader_kwargs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        config = ERPConnectionConfig(erp_type=erp_type, base_url="file://local")
        super().__init__(config)
        self._source_files = [Path(f) for f in source_files]
        self._erp_version = erp_version
        self._format_hints = format_hints or {}
        self._reader_kwargs = reader_kwargs or {}
        self._reader = FileFormatReader()
        self._cached_data: dict[str, list[dict[str, Any]]] = {}

    @property
    def erp_type(self) -> ERPType:
        return self.config.erp_type

    async def extract(self) -> ERPMetadata:
        from datetime import datetime, timezone

        entities: list[EntityMetadata] = []

        for file_path in self._source_files:
            hint = self._format_hints.get(str(file_path))
            kwargs = self._reader_kwargs.get(str(file_path), {})
            result = self._reader.read(file_path, format_hint=hint, **kwargs)

            entity_name = self._file_to_entity_name(file_path)
            self._cached_data[entity_name] = result.rows

            fields: list[FieldMetadata] = []
            for field_meta in result.inferred_fields:
                sample_vals = [
                    row.get(field_meta.name)
                    for row in result.rows[:5]
                    if row.get(field_meta.name) is not None
                ]
                fields.append(
                    FieldMetadata(
                        name=field_meta.name,
                        type=field_meta.type,
                        nullable=field_meta.nullable,
                        sample_values=sample_vals,
                        max_length=field_meta.max_length,
                        description=field_meta.name,
                    )
                )

            entities.append(
                EntityMetadata(
                    name=entity_name,
                    description=f"Extracted from {file_path.name} ({result.source_format})",
                    fields=fields,
                )
            )

        logger.info(
            "FileBasedExtractor: extracted %d entities from %d files",
            len(entities),
            len(self._source_files),
        )

        return ERPMetadata(
            source=self.config.erp_type,
            source_version=self._erp_version,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            entities=entities,
        )

    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        rows = self._cached_data.get(entity, [])
        result: dict[str, list[Any]] = {f: [] for f in fields}
        for row in rows[:limit]:
            for f in fields:
                if f in row and row[f] is not None:
                    result[f].append(row[f])
        return result

    @staticmethod
    def _file_to_entity_name(path: Path) -> str:
        stem = path.stem.lower()
        for prefix in ("sap_", "oracle_", "dynamics_", "netsuite_", "workday_"):
            if stem.startswith(prefix):
                stem = stem[len(prefix):]
                break
        parts = stem.split("_")
        return "".join(word.capitalize() for word in parts)
