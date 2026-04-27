"""LLM judge ensemble — three specialised judges for mapping quality assessment."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Awaitable
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], Awaitable[str]]


class JudgeResult(BaseModel):
    """Aggregated result from the 3-judge ensemble."""

    field_score: float = 0.0
    table_score: float = 0.0
    rule_score: float = 0.0
    aggregate: float = 0.0
    rationales: list[str] = Field(default_factory=list)


class MappingLLMJudge:
    """Three-judge ensemble for ERP-to-CDM mapping quality evaluation.

    The async LLM callable takes a single prompt string and returns a JSON string.
    """

    WEIGHT_FIELD: float = 0.40
    WEIGHT_TABLE: float = 0.35
    WEIGHT_RULE: float = 0.25

    def __init__(self, llm_callable: LLMCallable) -> None:
        self._llm = llm_callable

    async def judge_field(
        self, source_field: str, cdm_field: str, context: dict[str, Any]
    ) -> float:
        """Evaluate a single field-level mapping. Returns score 0-1."""
        prompt = (
            f"Rate this ERP-to-CDM field mapping on a scale of 0.0 to 1.0.\n"
            f"Source field: {source_field}\n"
            f"CDM field: {cdm_field}\n"
            f"Context: {json.dumps(context)}\n"
            f'Respond with JSON: {{"score": <float>, "rationale": "<string>"}}'
        )
        try:
            raw = await self._llm(prompt)
            data = json.loads(raw)
            return max(0.0, min(1.0, float(data.get("score", 0.0))))
        except Exception:
            logger.warning("Field judge failed for %s -> %s", source_field, cdm_field)
            return 0.0

    async def judge_table(
        self, source_entity: str, cdm_entity: str, context: dict[str, Any]
    ) -> float:
        """Evaluate entity/table-level mapping. Returns score 0-1."""
        prompt = (
            f"Rate this entity mapping on a scale of 0.0 to 1.0.\n"
            f"Source entity: {source_entity}\n"
            f"CDM entity: {cdm_entity}\n"
            f"Context: {json.dumps(context)}\n"
            f'Respond with JSON: {{"score": <float>, "rationale": "<string>"}}'
        )
        try:
            raw = await self._llm(prompt)
            data = json.loads(raw)
            return max(0.0, min(1.0, float(data.get("score", 0.0))))
        except Exception:
            logger.warning("Table judge failed for %s -> %s", source_entity, cdm_entity)
            return 0.0

    async def judge_business_rules(self, context: dict[str, Any]) -> float:
        """Evaluate whether mappings preserve business rules. Returns score 0-1."""
        prompt = (
            f"Rate whether these mappings preserve accounting business rules (0.0 to 1.0).\n"
            f"Context: {json.dumps(context)}\n"
            f'Respond with JSON: {{"score": <float>, "rationale": "<string>"}}'
        )
        try:
            raw = await self._llm(prompt)
            data = json.loads(raw)
            return max(0.0, min(1.0, float(data.get("score", 0.0))))
        except Exception:
            logger.warning("Business rule judge failed")
            return 0.0

    async def judge_all(
        self,
        source_field: str,
        cdm_field: str,
        source_entity: str,
        cdm_entity: str,
        context: dict[str, Any],
    ) -> JudgeResult:
        """Run all three judges and return the weighted aggregate."""
        field_score = await self.judge_field(source_field, cdm_field, context)
        table_score = await self.judge_table(source_entity, cdm_entity, context)
        rule_score = await self.judge_business_rules(context)

        aggregate = (
            self.WEIGHT_FIELD * field_score
            + self.WEIGHT_TABLE * table_score
            + self.WEIGHT_RULE * rule_score
        )

        return JudgeResult(
            field_score=round(field_score, 4),
            table_score=round(table_score, 4),
            rule_score=round(rule_score, 4),
            aggregate=round(aggregate, 4),
            rationales=[
                f"Field: {field_score:.3f}",
                f"Table: {table_score:.3f}",
                f"Rule: {rule_score:.3f}",
            ],
        )
