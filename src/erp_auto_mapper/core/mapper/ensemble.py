"""Mapping Ensemble — combines all three passes into a final scored result."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class ConfidenceBand(str, Enum):
    AUTO = "auto"
    REVIEW = "review"
    MANUAL = "manual"


class MappingResult(BaseModel):
    """Final mapping result for a single source field."""

    source_field: str = ""
    cdm_field: str = ""
    confidence: float = 0.0
    band: ConfidenceBand = ConfidenceBand.MANUAL

    @staticmethod
    def classify_confidence(score: float) -> ConfidenceBand:
        if score >= 0.85:
            return ConfidenceBand.AUTO
        if score >= 0.50:
            return ConfidenceBand.REVIEW
        return ConfidenceBand.MANUAL


_W_STRING: float = 0.20
_W_SEMANTIC: float = 0.35
_W_TYPE: float = 0.15
_W_SAMPLE: float = 0.20
_W_STRUCTURAL: float = 0.10


class MappingEnsemble:
    """Orchestrates all three mapping passes and produces weighted scores."""

    LLM_CAP: float = 0.70

    def __init__(self) -> None:
        pass

    def _compute_weighted_score(
        self,
        string_sim: float = 0.0,
        semantic_sim: float = 0.0,
        type_match: float = 0.0,
        sample_overlap: float = 0.0,
        structural: float = 0.0,
    ) -> float:
        return round(
            _W_STRING * string_sim
            + _W_SEMANTIC * semantic_sim
            + _W_TYPE * type_match
            + _W_SAMPLE * sample_overlap
            + _W_STRUCTURAL * structural,
            4,
        )

    def _apply_llm_cap(
        self,
        confidence: float,
        has_embedding_confirmation: bool = False,
        has_type_confirmation: bool = False,
        has_sample_confirmation: bool = False,
    ) -> float:
        """Apply CTRL-5: LLM-only mappings capped at 0.7."""
        if not has_embedding_confirmation and not has_type_confirmation and not has_sample_confirmation:
            return min(confidence, self.LLM_CAP)
        return confidence
