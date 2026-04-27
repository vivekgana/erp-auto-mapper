"""Bronze zone writer — ingests raw ERP data into Delta bronze tables."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BronzeIngestResult(BaseModel):
    table_name: str
    rows_written: int
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = Field(default_factory=dict)


class BronzeWriter:
    """Writes raw ERP records to a bronze Delta table via DeltaClient."""

    def __init__(self, delta_client: Any, catalog: str = "erp_auto_mapper_dev", schema: str = "mapper") -> None:
        self._client = delta_client
        self._catalog = catalog
        self._schema = schema

    def write(
        self,
        table_suffix: str,
        records: list[dict[str, Any]],
        source_metadata: dict[str, Any] | None = None,
    ) -> BronzeIngestResult:
        table = f"{self._catalog}.{self._schema}.bronze_{table_suffix}"

        rows = []
        for record in records:
            rows.append({
                "raw_json": json.dumps(record),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "source_metadata": json.dumps(source_metadata or {}),
            })

        written = self._client.write_rows(table, rows)
        logger.info("Wrote %d rows to %s", written, table)

        return BronzeIngestResult(
            table_name=table,
            rows_written=written,
            metadata=source_metadata or {},
        )
