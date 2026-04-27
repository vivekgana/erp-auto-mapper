"""Regression detector — flags mapping quality degradation against stored baselines."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Local eval result type (self-contained)
# ------------------------------------------------------------------

class MappingEvalResult(BaseModel):
    """Mirrors the scorer's eval result for decoupled baseline storage."""

    per_dimension: dict[str, float] = Field(default_factory=dict)
    aggregate: float = 0.0
    passed: bool = False
    rationale: str = ""


# ------------------------------------------------------------------
# Result model
# ------------------------------------------------------------------

class DimensionRegression(BaseModel):
    """Details of a single dimension's regression."""

    dimension: str
    baseline_score: float
    current_score: float
    delta_pct: float


class RegressionResult(BaseModel):
    """Outcome of a regression check."""

    has_regression: bool = False
    degraded_dimensions: list[str] = Field(default_factory=list)
    degradation_details: list[DimensionRegression] = Field(default_factory=list)
    recommendation: str = ""


class RegressionDetector:
    """Compares current mapping eval scores against stored baselines.

    A regression is flagged when **any** dimension score drops more than
    the configured threshold (default 10 %) relative to the baseline.
    """

    DEGRADATION_THRESHOLD_PCT: float = 10.0

    def __init__(self) -> None:
        self._baselines: dict[str, MappingEvalResult] = {}

    # ------------------------------------------------------------------
    # Baseline management
    # ------------------------------------------------------------------

    def store_baseline(self, baseline_id: str, result: MappingEvalResult) -> None:
        """Persist a baseline eval result under *baseline_id*."""
        self._baselines[baseline_id] = result
        logger.info("Stored baseline '%s' (aggregate=%.4f)", baseline_id, result.aggregate)

    def get_baseline(self, baseline_id: str) -> MappingEvalResult | None:
        return self._baselines.get(baseline_id)

    def list_baselines(self) -> list[str]:
        return list(self._baselines.keys())

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(
        self, current: MappingEvalResult, baseline: MappingEvalResult | str
    ) -> RegressionResult:
        """Compare *current* scores against *baseline*.

        *baseline* can be a ``MappingEvalResult`` directly or a baseline_id string
        for look-up from stored baselines.
        """
        if isinstance(baseline, str):
            resolved = self._baselines.get(baseline)
            if resolved is None:
                return RegressionResult(
                    has_regression=False,
                    recommendation=f"No baseline '{baseline}' found.",
                )
            baseline = resolved

        degraded: list[DimensionRegression] = []

        for dim, baseline_score in baseline.per_dimension.items():
            current_score = current.per_dimension.get(dim, 0.0)
            if baseline_score == 0.0:
                continue
            delta_pct = ((baseline_score - current_score) / baseline_score) * 100.0
            if delta_pct > self.DEGRADATION_THRESHOLD_PCT:
                degraded.append(DimensionRegression(
                    dimension=dim,
                    baseline_score=round(baseline_score, 4),
                    current_score=round(current_score, 4),
                    delta_pct=round(delta_pct, 2),
                ))

        if baseline.aggregate > 0.0:
            agg_delta_pct = ((baseline.aggregate - current.aggregate) / baseline.aggregate) * 100.0
            if agg_delta_pct > self.DEGRADATION_THRESHOLD_PCT:
                degraded.append(DimensionRegression(
                    dimension="aggregate",
                    baseline_score=round(baseline.aggregate, 4),
                    current_score=round(current.aggregate, 4),
                    delta_pct=round(agg_delta_pct, 2),
                ))

        has_regression = len(degraded) > 0
        recommendation = self._build_recommendation(degraded) if has_regression else "No regression detected."

        return RegressionResult(
            has_regression=has_regression,
            degraded_dimensions=[d.dimension for d in degraded],
            degradation_details=degraded,
            recommendation=recommendation,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _build_recommendation(degraded: list[DimensionRegression]) -> str:
        """Generate a human-readable recommendation from degraded dimensions."""
        dim_names = [d.dimension for d in degraded]
        worst = max(degraded, key=lambda d: d.delta_pct)
        parts = [
            f"Regression detected in {len(degraded)} dimension(s): {', '.join(dim_names)}.",
            f"Worst degradation: '{worst.dimension}' dropped {worst.delta_pct:.1f}% "
            f"(from {worst.baseline_score:.4f} to {worst.current_score:.4f}).",
            "Recommend: review recent mapping changes, check for schema drift, "
            "and re-run the golden-set evaluator.",
        ]
        return " ".join(parts)
