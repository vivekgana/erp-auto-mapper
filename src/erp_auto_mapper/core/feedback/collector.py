"""FeedbackCollector — capture human corrections from mapping results."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from erp_auto_mapper.core.feedback.store import FeedbackEntry, FeedbackStore

logger = logging.getLogger(__name__)


class FeedbackCollector:
    """Captures human feedback on mapping results and routes to FeedbackStore."""

    def __init__(self, store: FeedbackStore) -> None:
        self._store = store

    def record_correction(
        self,
        source_field: str,
        original_cdm_field: str,
        corrected_cdm_field: str,
        *,
        source_entity: str = "",
        erp_type: str = "",
        engagement_id: str = "",
        reviewer: str = "",
        context: dict[str, Any] | None = None,
    ) -> FeedbackEntry:
        """Record a human correction: the mapper chose wrong, human provides correct target."""
        entry = FeedbackEntry(
            source_field=source_field,
            original_cdm_field=original_cdm_field,
            corrected_cdm_field=corrected_cdm_field,
            feedback_type="correction",
            source_entity=source_entity,
            erp_type=erp_type,
            engagement_id=engagement_id,
            reviewer=reviewer,
            timestamp=datetime.now(timezone.utc).isoformat(),
            context=context or {},
        )
        self._store.record_feedback(entry)
        return entry

    def record_confirmation(
        self,
        source_field: str,
        cdm_field: str,
        *,
        source_entity: str = "",
        erp_type: str = "",
        engagement_id: str = "",
        reviewer: str = "",
    ) -> FeedbackEntry:
        """Record a human confirmation: the mapper was right."""
        entry = FeedbackEntry(
            source_field=source_field,
            original_cdm_field=cdm_field,
            corrected_cdm_field=cdm_field,
            feedback_type="confirmation",
            source_entity=source_entity,
            erp_type=erp_type,
            engagement_id=engagement_id,
            reviewer=reviewer,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._store.record_feedback(entry)
        return entry

    def record_rejection(
        self,
        source_field: str,
        cdm_field: str,
        *,
        source_entity: str = "",
        erp_type: str = "",
        engagement_id: str = "",
        reviewer: str = "",
    ) -> FeedbackEntry:
        """Record a human rejection: the mapper was wrong but no correction provided."""
        entry = FeedbackEntry(
            source_field=source_field,
            original_cdm_field=cdm_field,
            feedback_type="rejection",
            source_entity=source_entity,
            erp_type=erp_type,
            engagement_id=engagement_id,
            reviewer=reviewer,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._store.record_feedback(entry)
        return entry

    def collect_from_mapping_output(
        self,
        entity_mappings: list[dict[str, Any]],
        corrections: dict[str, str],
        *,
        erp_type: str = "",
        engagement_id: str = "",
        reviewer: str = "",
    ) -> list[FeedbackEntry]:
        """Bulk-collect feedback from mapping output + human correction map.

        Args:
            entity_mappings: Field mappings from the orchestrator output.
            corrections: Dict of {source_field: corrected_cdm_field} from human review.
            erp_type: ERP system type.
            engagement_id: Engagement identifier.
            reviewer: Human reviewer identifier.

        Returns:
            List of recorded feedback entries.
        """
        entries: list[FeedbackEntry] = []
        for fm in entity_mappings:
            source = fm.get("source_field", "")
            original = fm.get("cdm_field", "")
            if not source:
                continue

            if source in corrections:
                corrected = corrections[source]
                if corrected != original:
                    entry = self.record_correction(
                        source, original, corrected,
                        erp_type=erp_type,
                        engagement_id=engagement_id,
                        reviewer=reviewer,
                    )
                else:
                    entry = self.record_confirmation(
                        source, original,
                        erp_type=erp_type,
                        engagement_id=engagement_id,
                        reviewer=reviewer,
                    )
                entries.append(entry)

        return entries
