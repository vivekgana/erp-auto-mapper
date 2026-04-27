"""DLT (Delta Live Tables) integration adapter."""

from __future__ import annotations

from typing import Any

from erp_auto_mapper.core.integrations.base import BaseIntegrationAdapter, IntegrationConfig, IntegrationOutput


class DLTAdapter(BaseIntegrationAdapter):
    """Generates DLT pipeline definitions for mapping runs."""

    def __init__(self, config: IntegrationConfig) -> None:
        self._config = config

    async def execute(self, data: dict[str, Any]) -> IntegrationOutput:
        pipeline_spec = {
            "name": f"erp-auto-mapper-{data.get('engagement_id', 'default')}",
            "catalog": self._config.catalog,
            "target": self._config.schema_name,
            "tables": [
                {"name": "erp_mapping_runs", "type": "streaming"},
                {"name": "erp_mapping_results", "type": "streaming"},
                {"name": "erp_eval_reports", "type": "streaming"},
            ],
        }
        return IntegrationOutput(
            platform="dlt",
            code="",
            metadata=pipeline_spec,
        )
