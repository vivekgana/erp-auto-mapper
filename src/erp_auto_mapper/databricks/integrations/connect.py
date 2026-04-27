"""Databricks Connect integration adapter."""

from __future__ import annotations

from typing import Any

from erp_auto_mapper.core.integrations.base import BaseIntegrationAdapter, IntegrationConfig, IntegrationOutput


class ConnectAdapter(BaseIntegrationAdapter):
    """Executes mapping via Databricks Connect (remote Spark)."""

    def __init__(self, config: IntegrationConfig) -> None:
        self._config = config

    async def execute(self, data: dict[str, Any]) -> IntegrationOutput:
        return IntegrationOutput(
            platform="connect",
            code="",
            metadata={"message": "Databricks Connect adapter placeholder", "config": self._config.model_dump()},
        )
