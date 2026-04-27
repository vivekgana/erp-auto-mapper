"""ETL Skill protocol, shared context, and pipeline orchestrator."""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SkillResult(BaseModel):
    """Standardized output from any ETL skill."""

    model_config = {"arbitrary_types_allowed": True}

    skill_name: str
    status: str = "success"
    output: Any = None
    metrics: dict[str, float] = Field(default_factory=dict)
    duration_ms: float = 0.0
    error: str = ""


class SkillContext(BaseModel):
    """Shared mutable context passed between skills in a pipeline."""

    model_config = {"arbitrary_types_allowed": True}

    engagement_id: str
    erp_type: str = "sap"
    metadata: Any = None
    entity_mappings: list[Any] = Field(default_factory=list)
    eval_report: dict[str, Any] = Field(default_factory=dict)
    platform: str = "databricks"
    generated_code: Any = None
    load_result: Any = None
    config: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ETLSkill(Protocol):
    @property
    def name(self) -> str: ...

    async def execute(self, context: SkillContext) -> SkillResult: ...


class PipelineResult(BaseModel):
    """Aggregated result from a full pipeline run."""

    model_config = {"arbitrary_types_allowed": True}

    engagement_id: str
    status: str = "success"
    skill_results: list[SkillResult] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    context: Any = None


class ETLPipeline:
    """Compose and execute ETL skills sequentially with shared context."""

    def __init__(
        self,
        skills: list[ETLSkill],
        feedback_collector: Any = None,
    ) -> None:
        self._skills = skills
        self._feedback = feedback_collector

    async def run(self, context: SkillContext) -> PipelineResult:
        start = time.time()
        results: list[SkillResult] = []

        for skill in self._skills:
            skill_start = time.time()
            try:
                result = await skill.execute(context)
                result.duration_ms = (time.time() - skill_start) * 1000
                results.append(result)

                if result.status == "failed":
                    logger.error(
                        "Skill '%s' failed: %s — aborting pipeline",
                        skill.name,
                        result.error,
                    )
                    break

                logger.info(
                    "Skill '%s' completed in %.0fms",
                    skill.name,
                    result.duration_ms,
                )
            except Exception as e:
                logger.error("Skill '%s' raised exception: %s", skill.name, e)
                results.append(
                    SkillResult(
                        skill_name=skill.name,
                        status="failed",
                        error=str(e),
                        duration_ms=(time.time() - skill_start) * 1000,
                    )
                )
                break

        total_ms = (time.time() - start) * 1000
        all_ok = all(r.status == "success" for r in results)

        return PipelineResult(
            engagement_id=context.engagement_id,
            status="success" if all_ok else "failed",
            skill_results=results,
            total_duration_ms=round(total_ms, 1),
            context=context,
        )
