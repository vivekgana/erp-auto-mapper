"""Golden-set evaluator — scores mappings against verified ground-truth examples."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from erp_auto_mapper.core.extractors.base import ERPType

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Local mapping types (self-contained)
# ------------------------------------------------------------------

class FieldMapping(BaseModel):
    source_field: str
    source_type: str = ""
    target_field: str
    target_type: str = ""
    confidence: float = 0.0


class MappingResult(BaseModel):
    source_entity: str
    target_entity: str
    erp_type: ERPType = ERPType.SAP
    field_mappings: list[FieldMapping] = Field(default_factory=list)
    overall_confidence: float = 0.0


# ------------------------------------------------------------------
# Result model
# ------------------------------------------------------------------

class GoldenSetResult(BaseModel):
    """Evaluation result against the golden set."""

    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    details: list[str] = Field(default_factory=list)

    def threshold_met(self, threshold: float = 0.85) -> bool:
        """Return True if F1 meets the given threshold."""
        return self.f1 >= threshold


# ------------------------------------------------------------------
# Golden-set store
# ------------------------------------------------------------------

class _GoldenMapping(BaseModel):
    """A single verified field mapping in the golden set."""

    source_entity: str
    source_field: str
    target_entity: str
    target_field: str


class GoldenSetEvaluator:
    """Maintains verified mapping examples per ERP type and scores new mappings.

    Evaluation follows the Valentine benchmark methodology: precision, recall,
    and F1 are computed over (source_field, target_field) pairs per entity.
    The default pass threshold is F1 >= 0.85.
    """

    F1_THRESHOLD: float = 0.85

    def __init__(self) -> None:
        self._golden_sets: dict[ERPType, list[_GoldenMapping]] = {}

    # ------------------------------------------------------------------
    # Golden-set management
    # ------------------------------------------------------------------

    def register_golden_set(
        self,
        erp_type: ERPType,
        mappings: list[dict[str, str]],
    ) -> None:
        """Register verified ground-truth mappings for an ERP type.

        Each mapping dict must contain ``source_entity``, ``source_field``,
        ``target_entity``, and ``target_field``.
        """
        golden = [
            _GoldenMapping(
                source_entity=m["source_entity"],
                source_field=m["source_field"],
                target_entity=m["target_entity"],
                target_field=m["target_field"],
            )
            for m in mappings
        ]
        self._golden_sets[erp_type] = golden
        logger.info(
            "Registered %d golden mappings for ERP type '%s'",
            len(golden),
            erp_type.value,
        )

    def has_golden_set(self, erp_type: ERPType) -> bool:
        return erp_type in self._golden_sets and len(self._golden_sets[erp_type]) > 0

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        predicted: list[dict[str, str]] | list[MappingResult],
        golden: list[dict[str, str]] | ERPType,
        erp_type: ERPType | None = None,
    ) -> GoldenSetResult:
        """Score *predicted* mappings against *golden* ground-truth.

        Supports two calling conventions:
        1. ``evaluate(predicted_dicts, golden_dicts, erp_type)`` — simple dict lists
        2. ``evaluate(mapping_results, erp_type)`` — MappingResult objects + registered golden set
        """
        predicted_pairs: set[tuple[str, ...]]
        golden_pairs: set[tuple[str, ...]]

        if isinstance(golden, ERPType):
            erp_type = golden
            golden_dicts: list[dict[str, str]] = []
        else:
            golden_dicts = golden

        if isinstance(golden, list):
            predicted_pairs = {
                (d.get("source", ""), d.get("cdm", ""))
                for d in predicted
                if isinstance(d, dict)
            }
            golden_pairs = {
                (d.get("source", ""), d.get("cdm", ""))
                for d in golden_dicts
            }
        else:
            stored_golden = self._golden_sets.get(erp_type or ERPType.SAP, [])
            if not stored_golden:
                return GoldenSetResult()
            mapping_results: list[MappingResult] = [
                p for p in predicted if isinstance(p, MappingResult)
            ]
            predicted_pairs = self._extract_pairs(mapping_results)
            golden_pairs = self._extract_golden_pairs(stored_golden)

        tp = predicted_pairs & golden_pairs
        fp = predicted_pairs - golden_pairs
        fn = golden_pairs - predicted_pairs

        true_positives = len(tp)
        false_positives = len(fp)
        false_negatives = len(fn)

        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        return GoldenSetResult(
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            true_positives=true_positives,
            false_positives=false_positives,
            false_negatives=false_negatives,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_pairs(
        mappings: list[MappingResult],
    ) -> set[tuple[str, ...]]:
        """Extract (source_entity, source_field, target_entity, target_field) tuples."""
        pairs: set[tuple[str, ...]] = set()
        for m in mappings:
            for fm in m.field_mappings:
                pairs.add((m.source_entity, fm.source_field, m.target_entity, fm.target_field))
        return pairs

    @staticmethod
    def _extract_golden_pairs(
        golden: list[_GoldenMapping],
    ) -> set[tuple[str, ...]]:
        """Extract (source_entity, source_field, target_entity, target_field) from golden set."""
        pairs: set[tuple[str, ...]] = set()
        for g in golden:
            pairs.add((g.source_entity, g.source_field, g.target_entity, g.target_field))
        return pairs
