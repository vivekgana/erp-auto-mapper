"""Snowflake integration adapter — write mapping results to Snowflake tables."""

from __future__ import annotations

from typing import Any

from erp_auto_mapper.core.integrations.base import BaseIntegrationAdapter, IntegrationConfig, IntegrationOutput


class SnowflakeAdapter(BaseIntegrationAdapter):
    """Writes mapping output to Snowflake via external connection."""

    def __init__(self, config: IntegrationConfig) -> None:
        self._config = config

    async def execute(self, data: dict[str, Any]) -> IntegrationOutput:
        return IntegrationOutput(
            platform="snowflake",
            code="",
            metadata={"message": "Snowflake adapter placeholder", "config": self._config.model_dump()},
        )
