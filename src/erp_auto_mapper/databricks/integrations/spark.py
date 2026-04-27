"""Spark integration adapter — for local or cluster-based Spark execution."""

from __future__ import annotations

from typing import Any

from erp_auto_mapper.core.integrations.base import BaseIntegrationAdapter, IntegrationConfig, IntegrationOutput


class SparkAdapter(BaseIntegrationAdapter):
    """Runs mapping pipeline on a Spark cluster."""

    def __init__(self, config: IntegrationConfig) -> None:
        self._config = config

    async def execute(self, data: dict[str, Any]) -> IntegrationOutput:
        return IntegrationOutput(
            platform="spark",
            code="",
            metadata={"message": "Spark adapter placeholder", "config": self._config.model_dump()},
        )
