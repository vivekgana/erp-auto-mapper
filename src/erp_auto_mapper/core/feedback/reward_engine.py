"""RewardEngine — Thompson Sampling contextual bandit for mapping arm selection."""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RewardSignal(BaseModel):
    """A reward observation for a mapping decision."""

    engagement_id: str = ""
    source_field: str
    cdm_field: str
    reward: float
    erp_type: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class ArmStats(BaseModel):
    """Beta distribution parameters for Thompson Sampling."""

    alpha: float = 1.0
    beta: float = 1.0
    observations: int = 0

    def sample(self) -> float:
        return random.betavariate(self.alpha, self.beta)

    def expected(self) -> float:
        return self.alpha / (self.alpha + self.beta)


class RewardEngine:
    """Thompson Sampling contextual bandit for mapping arm selection.

    Context key = (erp_type, source_field).
    Arms = candidate CDM fields.
    Reward = eval score (0-1) from MappingScorer, golden set F1, or human feedback.
    """

    def __init__(self, boost_scale: float = 0.10) -> None:
        self._arms: dict[str, dict[str, ArmStats]] = defaultdict(
            lambda: defaultdict(ArmStats)
        )
        self._boost_scale = boost_scale

    def _context_key(self, erp_type: str, source_field: str) -> str:
        return f"{erp_type}::{source_field}"

    def suggest_boost(
        self,
        erp_type: str,
        source_field: str,
        candidates: list[str],
    ) -> dict[str, float]:
        """Sample from posterior for each candidate, return score adjustments.

        Arms with more positive reward history get higher boosts.
        Arms with no observations get neutral (0.0) boost.
        """
        key = self._context_key(erp_type, source_field)
        arm_stats = self._arms.get(key)
        if not arm_stats:
            return {c: 0.0 for c in candidates}

        boosts: dict[str, float] = {}
        for cdm_field in candidates:
            stats = arm_stats.get(cdm_field)
            if stats is None or stats.observations == 0:
                boosts[cdm_field] = 0.0
            else:
                sampled = stats.sample()
                boost = (sampled - 0.5) * 2 * self._boost_scale
                boosts[cdm_field] = round(boost, 4)

        return boosts

    def suggest_deterministic(
        self,
        erp_type: str,
        source_field: str,
        candidates: list[str],
    ) -> dict[str, float]:
        """Return expected (mean) boost — deterministic, for testing."""
        key = self._context_key(erp_type, source_field)
        arm_stats = self._arms.get(key)
        if not arm_stats:
            return {c: 0.0 for c in candidates}

        boosts: dict[str, float] = {}
        for cdm_field in candidates:
            stats = arm_stats.get(cdm_field)
            if stats is None or stats.observations == 0:
                boosts[cdm_field] = 0.0
            else:
                expected = stats.expected()
                boost = (expected - 0.5) * 2 * self._boost_scale
                boosts[cdm_field] = round(boost, 4)

        return boosts

    def record_reward(self, signal: RewardSignal) -> None:
        """Update the bandit posterior for the chosen arm."""
        key = self._context_key(signal.erp_type, signal.source_field)
        stats = self._arms[key][signal.cdm_field]

        reward = max(0.0, min(1.0, signal.reward))
        stats.alpha += reward
        stats.beta += 1.0 - reward
        stats.observations += 1

        logger.debug(
            "Reward recorded: %s -> %s = %.3f (alpha=%.2f, beta=%.2f, n=%d)",
            signal.source_field,
            signal.cdm_field,
            reward,
            stats.alpha,
            stats.beta,
            stats.observations,
        )

    def get_stats(
        self, erp_type: str, source_field: str, cdm_field: str
    ) -> ArmStats | None:
        key = self._context_key(erp_type, source_field)
        arm_stats = self._arms.get(key)
        if arm_stats is None:
            return None
        return arm_stats.get(cdm_field)

    def total_observations(self) -> int:
        return sum(
            stats.observations
            for arms in self._arms.values()
            for stats in arms.values()
        )

    def clear(self) -> None:
        self._arms.clear()
