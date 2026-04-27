"""ValidateQualitySkill — 6-dimension eval + golden set + regression detection."""

from __future__ import annotations

import logging
from typing import Any

from erp_auto_mapper.core.eval.golden_set_evaluator import GoldenSetEvaluator
from erp_auto_mapper.core.eval.mapping_scorer import MappingInput, MappingScorer
from erp_auto_mapper.core.eval.regression_detector import (
    MappingEvalResult as RegMappingEvalResult,
    RegressionDetector,
)
from erp_auto_mapper.core.feedback.reward_engine import RewardEngine, RewardSignal
from erp_auto_mapper.core.skills.base import SkillContext, SkillResult

logger = logging.getLogger(__name__)


class ValidateQualitySkill:
    """Run the full evaluation scorecard on mapping results."""

    def __init__(
        self,
        threshold: float = 0.85,
        golden_set: list[dict[str, str]] | None = None,
        baseline_id: str | None = None,
        reward_engine: RewardEngine | None = None,
    ) -> None:
        self._threshold = threshold
        self._golden_set = golden_set
        self._baseline_id = baseline_id
        self._reward = reward_engine

    @property
    def name(self) -> str:
        return "validate_quality"

    async def execute(self, context: SkillContext) -> SkillResult:
        entity_mappings = context.entity_mappings
        if not entity_mappings:
            return SkillResult(
                skill_name=self.name,
                status="failed",
                error="No entity_mappings in context — run MapFieldsSkill first",
            )

        golden_pairs: set[tuple[str, str]] = set()
        if self._golden_set:
            for g in self._golden_set:
                golden_pairs.add((g.get("source", ""), g.get("cdm", "")))

        field_scores: list[dict[str, Any]] = []

        for em in entity_mappings:
            for fm in em.field_mappings:
                confidence = fm.get("confidence", 0.0)
                gs_match = 1.0 if (fm["source_field"], fm["cdm_field"]) in golden_pairs else None
                scorer = MappingScorer(
                    golden_set_score=gs_match,
                )
                inp = MappingInput(
                    source_field=fm["source_field"],
                    cdm_field=fm["cdm_field"],
                    source_type=fm.get("source_type", ""),
                    cdm_type=fm.get("cdm_type", ""),
                    mapping_confidence=confidence,
                )
                result = scorer.score(inp)
                field_scores.append({
                    "source_field": fm["source_field"],
                    "cdm_field": fm["cdm_field"],
                    "per_dimension": result.per_dimension,
                    "aggregate": result.aggregate,
                    "passed": result.passed,
                })

        avg_aggregate = (
            sum(s["aggregate"] for s in field_scores) / len(field_scores)
            if field_scores
            else 0.0
        )

        report: dict[str, Any] = {
            "field_scores": field_scores,
            "aggregate": round(avg_aggregate, 4),
            "total_fields": len(field_scores),
            "fields_passed": sum(1 for s in field_scores if s["passed"]),
            "threshold": self._threshold,
            "gate_passed": avg_aggregate >= self._threshold,
        }

        if self._golden_set:
            all_predicted = [
                {"source": fm["source_field"], "cdm": fm["cdm_field"]}
                for em in entity_mappings
                for fm in em.field_mappings
            ]
            gs_eval = GoldenSetEvaluator()
            gs_result = gs_eval.evaluate(all_predicted, self._golden_set)
            report["golden_set"] = gs_result.model_dump()

        if self._baseline_id:
            detector = RegressionDetector()
            current = RegMappingEvalResult(
                per_dimension={"aggregate": avg_aggregate},
                aggregate=avg_aggregate,
                passed=avg_aggregate >= self._threshold,
            )
            reg_result = detector.detect(current, self._baseline_id)
            report["regression"] = reg_result.model_dump()

        if self._reward:
            for score_entry in field_scores:
                self._reward.record_reward(
                    RewardSignal(
                        engagement_id=context.engagement_id,
                        source_field=score_entry["source_field"],
                        cdm_field=score_entry["cdm_field"],
                        reward=score_entry["aggregate"],
                        erp_type=context.erp_type,
                    )
                )

        context.eval_report = report

        return SkillResult(
            skill_name=self.name,
            output=report,
            metrics={
                "aggregate": round(avg_aggregate, 4),
                "fields_passed": report["fields_passed"],
                "total_fields": report["total_fields"],
                "gate_passed": 1.0 if report["gate_passed"] else 0.0,
            },
        )
