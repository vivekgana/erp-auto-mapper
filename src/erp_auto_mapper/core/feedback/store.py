"""FeedbackStore — persistent mapping feedback with cross-engagement transfer learning."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_CORRECTION_BOOST = 0.15
_CORRECTION_PENALTY = -0.20
_CONFIRMATION_BOOST = 0.10
_REJECTION_PENALTY = -0.15


class FeedbackEntry(BaseModel):
    """A single piece of mapping feedback."""

    source_field: str
    original_cdm_field: str
    corrected_cdm_field: str = ""
    feedback_type: str = "correction"
    source_entity: str = ""
    erp_type: str = ""
    engagement_id: str = ""
    reviewer: str = ""
    reward: float = 0.0
    timestamp: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class FeedbackStore:
    """Stores mapping feedback for cross-engagement transfer learning.

    Feedback types:
    - correction: Human changed the mapping target
    - confirmation: Human approved a mapping (promotes confidence)
    - rejection: Human rejected a mapping without providing alternative
    """

    def __init__(self) -> None:
        self._entries: list[FeedbackEntry] = []
        self._by_erp_field: dict[str, dict[str, list[FeedbackEntry]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def record_feedback(self, entry: FeedbackEntry) -> None:
        if not entry.timestamp:
            entry.timestamp = datetime.now(timezone.utc).isoformat()
        self._entries.append(entry)
        self._by_erp_field[entry.erp_type][entry.source_field].append(entry)
        logger.info(
            "Recorded %s feedback: %s -> %s (was %s) [%s/%s]",
            entry.feedback_type,
            entry.source_field,
            entry.corrected_cdm_field or entry.original_cdm_field,
            entry.original_cdm_field,
            entry.erp_type,
            entry.engagement_id,
        )

    def get_priors(
        self, erp_type: str, source_field: str
    ) -> list[FeedbackEntry]:
        return list(self._by_erp_field.get(erp_type, {}).get(source_field, []))

    def compute_boost(
        self, erp_type: str, source_field: str, candidate_cdm: str
    ) -> float:
        """Compute score adjustment for a candidate CDM field based on accumulated feedback."""
        priors = self.get_priors(erp_type, source_field)
        if not priors:
            return 0.0

        boost = 0.0
        for entry in priors:
            if entry.feedback_type == "correction":
                if candidate_cdm == entry.corrected_cdm_field:
                    boost += _CORRECTION_BOOST
                elif candidate_cdm == entry.original_cdm_field:
                    boost += _CORRECTION_PENALTY
            elif entry.feedback_type == "confirmation":
                if candidate_cdm == entry.original_cdm_field:
                    boost += _CONFIRMATION_BOOST
            elif entry.feedback_type == "rejection":
                if candidate_cdm == entry.original_cdm_field:
                    boost += _REJECTION_PENALTY

        return round(max(-0.50, min(0.50, boost)), 4)

    def get_all_entries(self) -> list[FeedbackEntry]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
        self._by_erp_field.clear()
