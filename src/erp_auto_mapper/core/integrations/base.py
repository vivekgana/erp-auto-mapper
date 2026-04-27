"""Base integration adapter — Strategy pattern for multi-platform code generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from erp_auto_mapper.core.orchestrator import EntityMappingOutput, MappingOutput


class IntegrationConfig(BaseModel):
    """Base configuration for all integration adapters."""

    catalog: str = "cortex_dev_catalog"
    schema_name: str = "erp_auto_mapper"
    source_format: str = "delta"


class IntegrationOutput(BaseModel):
    """Output from an integration adapter."""

    platform: str
    code: str
    file_extension: str = ".py"
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseIntegrationAdapter(ABC):
    """Abstract base for platform-specific code generation.

    Each adapter translates MappingOutput into code/SQL consumable
    by a specific big data processing platform.
    """

    @property
    @abstractmethod
    def platform_name(self) -> str: ...

    @abstractmethod
    def generate(
        self, mapping_output: MappingOutput, config: IntegrationConfig | None = None
    ) -> IntegrationOutput: ...

    @staticmethod
    def _build_field_expressions(
        entity_mapping: EntityMappingOutput,
    ) -> list[tuple[str, str, str]]:
        """Return (source_field, cdm_field, transform_expression) tuples."""
        return [
            (
                fm.get("source_field", ""),
                fm.get("cdm_field", ""),
                fm.get("transform_expression", "direct") or "direct",
            )
            for fm in entity_mapping.field_mappings
        ]
