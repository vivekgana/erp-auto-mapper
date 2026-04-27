"""Multi-platform integration adapters for ERP mapping output."""

from __future__ import annotations

from erp_auto_mapper.core.integrations.base import (
    BaseIntegrationAdapter,
    IntegrationConfig,
    IntegrationOutput,
)
from erp_auto_mapper.core.integrations.databricks_connect import (
    DatabricksConnectAdapter,
    DatabricksConnectConfig,
)
from erp_auto_mapper.core.integrations.databricks_dlt import DatabricksDLTAdapter, DLTConfig
from erp_auto_mapper.core.integrations.snowflake import SnowflakeAdapter, SnowflakeConfig
from erp_auto_mapper.core.integrations.spark import SparkAdapter, SparkConfig

_ADAPTERS: dict[str, type[BaseIntegrationAdapter]] = {
    "databricks_dlt": DatabricksDLTAdapter,
    "databricks_connect": DatabricksConnectAdapter,
    "snowflake": SnowflakeAdapter,
    "spark": SparkAdapter,
}


def get_adapter(platform: str) -> BaseIntegrationAdapter:
    """Factory: return the adapter for a given platform name."""
    cls = _ADAPTERS.get(platform)
    if cls is None:
        raise ValueError(
            f"Unknown platform: {platform}. Available: {sorted(_ADAPTERS)}"
        )
    return cls()


__all__ = [
    "BaseIntegrationAdapter",
    "IntegrationConfig",
    "IntegrationOutput",
    "DatabricksDLTAdapter",
    "DLTConfig",
    "DatabricksConnectAdapter",
    "DatabricksConnectConfig",
    "SnowflakeAdapter",
    "SnowflakeConfig",
    "SparkAdapter",
    "SparkConfig",
    "get_adapter",
]
