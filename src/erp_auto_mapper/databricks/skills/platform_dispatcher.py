"""PlatformDispatcher — routes skill execution to the appropriate platform backend."""

from __future__ import annotations

import logging
from typing import Any

from erp_auto_mapper.core.skills.base import SkillContext, SkillResult

logger = logging.getLogger(__name__)


class PlatformDispatcher:
    """Dispatches ETL pipeline steps to Databricks-native or REST backends."""

    def __init__(self, delta_client: Any = None, use_model_serving: bool = False) -> None:
        self._delta_client = delta_client
        self._use_model_serving = use_model_serving

    async def dispatch(self, skill_name: str, context: SkillContext) -> SkillResult:
        logger.info("Dispatching skill '%s' to platform backend", skill_name)

        if skill_name == "load" and self._delta_client:
            from erp_auto_mapper.databricks.skills.load_skill import DeltaLoadSkill
            skill = DeltaLoadSkill(self._delta_client)
            return await skill.run(context)

        return SkillResult(
            skill_name=skill_name,
            status="failed",
            error=f"No platform handler for skill '{skill_name}'",
        )
