"""TransformGenerateSkill — platform-specific ETL code generation."""

from __future__ import annotations

import logging
from typing import Any

from erp_auto_mapper.core.orchestrator import EntityMappingOutput, MappingOutput
from erp_auto_mapper.core.skills.base import SkillContext, SkillResult
from erp_auto_mapper.core.transform.generator import TransformationGenerator

logger = logging.getLogger(__name__)


class TransformGenerateSkill:
    """Generate transformation SQL/code for a target platform."""

    def __init__(self, platform: str = "databricks") -> None:
        self._platform = platform
        self._transform_gen = TransformationGenerator()

    @property
    def name(self) -> str:
        return "transform_generate"

    async def execute(self, context: SkillContext) -> SkillResult:
        entity_mappings = context.entity_mappings
        if not entity_mappings:
            return SkillResult(
                skill_name=self.name,
                status="failed",
                error="No entity_mappings in context — run MapFieldsSkill first",
            )

        platform = self._platform or context.platform

        sql = self._generate_sql(entity_mappings)

        integration_output = self._generate_platform_code(
            entity_mappings, platform, context
        )

        context.generated_code = integration_output
        context.config["sql"] = sql

        return SkillResult(
            skill_name=self.name,
            output={"sql": sql, "platform_code": integration_output},
            metrics={
                "entities": len(entity_mappings),
            },
        )

    def _generate_sql(
        self, entity_mappings: list[EntityMappingOutput]
    ) -> dict[str, str]:
        staging_parts: list[str] = []
        transform_parts: list[str] = []
        mart_parts: list[str] = []

        for em in entity_mappings:
            mapping_dict: dict[str, Any] = {
                "source_table": em.source_entity,
                "cdm_entity": em.cdm_entity,
                "fields": [
                    {
                        "source": fm["source_field"],
                        "target": fm["cdm_field"],
                        "transform": fm.get("transform_expression", "direct")
                        or "direct",
                    }
                    for fm in em.field_mappings
                ],
            }
            output = self._transform_gen.generate_full(mapping_dict)
            staging_parts.append(output.sql_staging)
            transform_parts.append(output.sql_transform)
            mart_parts.append(output.sql_mart)

        return {
            "staging": "\n\n".join(staging_parts),
            "transform": "\n\n".join(transform_parts),
            "mart": "\n\n".join(mart_parts),
        }

    def _generate_platform_code(
        self,
        entity_mappings: list[EntityMappingOutput],
        platform: str,
        context: SkillContext,
    ) -> Any:
        from erp_auto_mapper.core.skills.platform_dispatcher import PlatformDispatcher

        mapping_output = MappingOutput(
            engagement_id=context.engagement_id,
            erp_type=context.erp_type,
            entity_mappings=entity_mappings,
        )

        dispatcher = PlatformDispatcher()
        return dispatcher.generate(mapping_output, platform)
