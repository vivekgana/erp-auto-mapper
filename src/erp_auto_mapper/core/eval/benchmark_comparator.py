"""Benchmark comparator — ranks mapping quality against historical results."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from erp_auto_mapper.core.extractors.base import ERPType

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Local eval result type (self-contained)
# ------------------------------------------------------------------

class MappingEvalResult(BaseModel):
    """Mirrors the scorer's eval result for decoupled comparison."""

    per_dimension: dict[str, float] = Field(default_factory=dict)
    aggregate: float = 0.0
    passed: bool = False
    rationale: str = ""


# ------------------------------------------------------------------
# Result model
# ------------------------------------------------------------------

class BenchmarkResult(BaseModel):
    """Result of comparing an eval against historical benchmarks."""

    percentile: float = 0.0
    comparison_count: int = 0
    above_average: bool = False
    mean_score: float = 0.0
    median_score: float = 0.0
    best_score: float = 0.0
    dimension_percentiles: dict[str, float] = Field(default_factory=dict)


class BenchmarkComparator:
    """Compares mapping evaluation quality against historical results for the same ERP type.

    Historical results are accumulated via :meth:`record` and percentile
    ranking is computed for new evaluations via :meth:`compare`.
    """

    def __init__(self) -> None:
        self._history: dict[ERPType, list[MappingEvalResult]] = {}

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def record(self, erp_type: ERPType, result: MappingEvalResult) -> None:
        """Add an eval result to the historical record for *erp_type*."""
        self._history.setdefault(erp_type, []).append(result)
        logger.info(
            "Recorded benchmark for '%s' (aggregate=%.4f, total=%d)",
            erp_type.value,
            result.aggregate,
            len(self._history[erp_type]),
        )

    def history_count(self, erp_type: ERPType) -> int:
        return len(self._history.get(erp_type, []))

    def clear_history(self, erp_type: ERPType) -> None:
        self._history.pop(erp_type, None)

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def compare(
        self, eval_result: MappingEvalResult, erp_type: ERPType
    ) -> BenchmarkResult:
        """Rank *eval_result* against historical results for *erp_type*.

        Returns percentile, whether the result is above average, and
        per-dimension percentile breakdowns.
        """
        history = self._history.get(erp_type, [])
        if not history:
            logger.warning("No historical benchmarks for ERP type '%s'", erp_type.value)
            return BenchmarkResult(
                comparison_count=0,
                above_average=True,  # First result is always "above average".
            )

        agg_scores = sorted(h.aggregate for h in history)
        count = len(agg_scores)

        percentile = self._compute_percentile(eval_result.aggregate, agg_scores)
        mean_score = sum(agg_scores) / count
        median_score = self._median(agg_scores)
        best_score = agg_scores[-1]

        # Per-dimension percentiles.
        dim_percentiles: dict[str, float] = {}
        all_dims = set(eval_result.per_dimension.keys())
        for h in history:
            all_dims.update(h.per_dimension.keys())

        for dim in all_dims:
            dim_scores = sorted(
                h.per_dimension.get(dim, 0.0) for h in history
            )
            current_dim_score = eval_result.per_dimension.get(dim, 0.0)
            dim_percentiles[dim] = self._compute_percentile(current_dim_score, dim_scores)

        return BenchmarkResult(
            percentile=round(percentile, 2),
            comparison_count=count,
            above_average=eval_result.aggregate >= mean_score,
            mean_score=round(mean_score, 4),
            median_score=round(median_score, 4),
            best_score=round(best_score, 4),
            dimension_percentiles={k: round(v, 2) for k, v in dim_percentiles.items()},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_percentile(value: float, sorted_scores: list[float]) -> float:
        """Compute the percentile rank of *value* within *sorted_scores*."""
        if not sorted_scores:
            return 100.0  # Only result => top percentile.
        count_below = sum(1 for s in sorted_scores if s < value)
        count_equal = sum(1 for s in sorted_scores if s == value)
        # Average rank percentile formula.
        percentile = ((count_below + 0.5 * count_equal) / len(sorted_scores)) * 100.0
        return min(100.0, max(0.0, percentile))

    @staticmethod
    def _median(sorted_values: list[float]) -> float:
        n = len(sorted_values)
        if n == 0:
            return 0.0
        mid = n // 2
        if n % 2 == 0:
            return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0
        return sorted_values[mid]
