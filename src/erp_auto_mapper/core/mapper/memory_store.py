"""Mapping Memory Store — persistent transfer-learning for field mappings."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from pydantic import BaseModel

from erp_auto_mapper.core.extractors.base import ERPType

logger = logging.getLogger(__name__)


class PriorMapping(BaseModel):
    """A prior mapping surfaced for transfer-learning."""

    source: str
    cdm: str
    erp_type: str = ""
    engagement_id: str = ""
    is_correction: bool = False
    original_cdm: str = ""


class MappingMemoryStore:
    """Tenant-isolated in-memory store for confirmed field mappings and corrections."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._corrections: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def store(
        self, engagement_id: str, mappings: list[dict[str, Any]]
    ) -> int:
        """Store confirmed mappings for an engagement."""
        self._store[engagement_id] = list(mappings)
        return len(mappings)

    def store_correction(
        self,
        engagement_id: str,
        source_field: str,
        original_cdm: str,
        corrected_cdm: str,
        erp_type: str = "",
    ) -> None:
        """Store a human correction for transfer learning."""
        self._corrections[engagement_id].append({
            "source": source_field,
            "original_cdm": original_cdm,
            "corrected_cdm": corrected_cdm,
            "erp_type": erp_type,
        })

    def retrieve_priors(
        self, erp_type: ERPType, field_name: str, engagement_id: str
    ) -> list[PriorMapping]:
        """Find prior confirmed mappings for a field within a specific engagement."""
        bucket = self._store.get(engagement_id, [])
        results: list[PriorMapping] = []
        for m in bucket:
            if m.get("source") == field_name:
                results.append(PriorMapping(
                    source=m.get("source", ""),
                    cdm=m.get("cdm", ""),
                    erp_type=m.get("erp_type", erp_type.value),
                    engagement_id=engagement_id,
                ))

        correction_bucket = self._corrections.get(engagement_id, [])
        for c in correction_bucket:
            if c.get("source") == field_name:
                results.append(PriorMapping(
                    source=c["source"],
                    cdm=c["corrected_cdm"],
                    erp_type=c.get("erp_type", erp_type.value),
                    engagement_id=engagement_id,
                    is_correction=True,
                    original_cdm=c["original_cdm"],
                ))

        return results

    def retrieve_cross_engagement(
        self, erp_type: str, field_name: str
    ) -> list[PriorMapping]:
        """Find priors across all engagements for a field + ERP type."""
        results: list[PriorMapping] = []
        for eng_id, bucket in self._store.items():
            for m in bucket:
                if m.get("source") == field_name:
                    results.append(PriorMapping(
                        source=m["source"],
                        cdm=m.get("cdm", ""),
                        erp_type=erp_type,
                        engagement_id=eng_id,
                    ))
        for eng_id, corr_bucket in self._corrections.items():
            for c in corr_bucket:
                if c.get("source") == field_name:
                    results.append(PriorMapping(
                        source=c["source"],
                        cdm=c["corrected_cdm"],
                        erp_type=erp_type,
                        engagement_id=eng_id,
                        is_correction=True,
                        original_cdm=c["original_cdm"],
                    ))
        return results

    def list_engagements(self) -> list[str]:
        all_ids = set(self._store.keys()) | set(self._corrections.keys())
        return sorted(all_ids)

    def count(self, engagement_id: str) -> int:
        return len(self._store.get(engagement_id, []))

    def correction_count(self, engagement_id: str) -> int:
        return len(self._corrections.get(engagement_id, []))

    def clear(self, engagement_id: str) -> int:
        removed = len(self._store.pop(engagement_id, []))
        removed += len(self._corrections.pop(engagement_id, []))
        return removed
