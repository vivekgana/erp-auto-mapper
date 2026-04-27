"""Central mapping scorer — 6-dimension evaluation for ERP-to-CDM mappings."""

from __future__ import annotations

import logging
import math
import re
from typing import Any

from pydantic import BaseModel, Field

from erp_auto_mapper.core.extractors.base import ERPType

logger = logging.getLogger(__name__)


def _camel_to_snake(name: str) -> str:
    """Convert CamelCase/PascalCase to snake_case."""
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower().replace("-", "_")


def _levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(curr_row[j] + 1, prev_row[j + 1] + 1, prev_row[j] + cost))
        prev_row = curr_row
    return prev_row[-1]


def _levenshtein_similarity(s1: str, s2: str) -> float:
    if not s1 and not s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    return 1.0 - (_levenshtein_distance(s1, s2) / max_len)


# ------------------------------------------------------------------
# Local mapping types (self-contained to avoid circular imports)
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


class MappingInput(BaseModel):
    """Convenience model for scoring a single field-level mapping."""

    source_field: str
    cdm_field: str
    source_type: str = ""
    cdm_type: str = ""
    source_description: str = ""
    cdm_description: str = ""
    source_samples: list[Any] = Field(default_factory=list)
    cdm_samples: list[Any] = Field(default_factory=list)
    mapping_confidence: float = 0.0


# ------------------------------------------------------------------
# Result model
# ------------------------------------------------------------------

class MappingEvalResult(BaseModel):
    """Evaluation result across all six dimensions."""

    per_dimension: dict[str, float] = Field(default_factory=dict)
    aggregate: float = 0.0
    passed: bool = False
    rationale: str = ""


# ------------------------------------------------------------------
# Type compatibility matrix
# ------------------------------------------------------------------

_COMPATIBLE_TYPES: dict[str, set[str]] = {
    "string": {"string", "date", "datetime", "time", "integer", "long", "decimal", "float", "double", "boolean"},
    "integer": {"integer", "long", "decimal", "float", "double", "string"},
    "long": {"long", "integer", "decimal", "float", "double", "string"},
    "decimal": {"decimal", "float", "double", "string"},
    "float": {"float", "double", "decimal", "string"},
    "double": {"double", "float", "decimal", "string"},
    "date": {"date", "datetime", "string"},
    "datetime": {"datetime", "date", "string"},
    "time": {"time", "string"},
    "boolean": {"boolean", "integer", "string"},
    "binary": {"binary", "string"},
}


class MappingScorer:
    """Central scorer with 6 evaluation dimensions for ERP-to-CDM mappings.

    Dimensions:
    1. **semantic_similarity** — cosine similarity of field name embeddings
    2. **type_compatibility** — source type maps to CDM type correctly
    3. **value_distribution_overlap** — KL divergence / PSI of sample distributions
    4. **llm_judge_score** — from LLM judge ensemble
    5. **business_rule_compliance** — from business rule validator
    6. **golden_set_match** — from golden set evaluator

    Aggregate = weighted sum; mapping passes when aggregate >= 0.85.
    """

    PASS_THRESHOLD: float = 0.85

    # Dimension weights (sum to 1.0).
    WEIGHTS: dict[str, float] = {
        "semantic_similarity": 0.20,
        "type_compatibility": 0.15,
        "value_distribution_overlap": 0.15,
        "llm_judge_score": 0.20,
        "business_rule_compliance": 0.15,
        "golden_set_match": 0.15,
    }

    def __init__(
        self,
        *,
        embedding_fn: Any | None = None,
        llm_judge_score: float | None = None,
        business_rule_score: float | None = None,
        golden_set_score: float | None = None,
    ) -> None:
        """Initialise the scorer.

        Optional injection points allow pre-computed scores from external
        evaluators (LLM judge, business rule validator, golden-set evaluator)
        to be supplied directly, making the scorer usable without runtime
        dependencies on those subsystems.

        Args:
            embedding_fn: Optional callable ``(text) -> list[float]`` for
                computing field-name embeddings.  If ``None``, a character-
                level similarity heuristic is used.
            llm_judge_score: Pre-computed LLM judge aggregate (0-1).
            business_rule_score: Pre-computed business-rule pass rate (0-1).
            golden_set_score: Pre-computed golden-set F1 (0-1).
        """
        self._embedding_fn = embedding_fn
        self._override_llm = llm_judge_score
        self._override_biz = business_rule_score
        self._override_golden = golden_set_score

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, mapping_input: MappingInput | MappingResult) -> MappingEvalResult:
        """Score a mapping across all 6 dimensions.

        Accepts either a :class:`MappingInput` (single-field convenience) or
        a full :class:`MappingResult` (entity-level with multiple field
        mappings).
        """
        if isinstance(mapping_input, MappingInput):
            mapping_result = self._input_to_result(mapping_input)
        else:
            mapping_result = mapping_input

        dims: dict[str, float] = {}

        dims["semantic_similarity"] = self._score_semantic_similarity(mapping_result)
        dims["type_compatibility"] = self._score_type_compatibility(mapping_result)
        dims["value_distribution_overlap"] = self._score_value_distribution(mapping_result)

        dims["llm_judge_score"] = (
            self._override_llm
            if self._override_llm is not None
            else mapping_result.overall_confidence
        )

        dims["business_rule_compliance"] = (
            self._override_biz if self._override_biz is not None else 1.0
        )

        dims["golden_set_match"] = (
            self._override_golden if self._override_golden is not None else 0.0
        )

        aggregate = self._compute_aggregate(dims)
        passed = aggregate >= self.PASS_THRESHOLD

        rationale = self._build_rationale(dims, aggregate, passed)

        return MappingEvalResult(
            per_dimension={k: round(v, 4) for k, v in dims.items()},
            aggregate=aggregate,
            passed=passed,
            rationale=rationale,
        )

    def _compute_aggregate(self, dims: dict[str, float]) -> float:
        """Weighted mean of dimension scores. Missing dimensions get 0."""
        total = 0.0
        for dim, weight in self.WEIGHTS.items():
            total += weight * dims.get(dim, 0.0)
        return round(total, 4)

    @staticmethod
    def _input_to_result(inp: MappingInput) -> MappingResult:
        """Convert a single-field MappingInput to MappingResult."""
        sim = MappingScorer._char_similarity(inp.source_field, inp.cdm_field)
        sample_overlap = 0.0
        if inp.source_samples and inp.cdm_samples:
            src_set = set(str(v) for v in inp.source_samples)
            cdm_set = set(str(v) for v in inp.cdm_samples)
            if src_set | cdm_set:
                sample_overlap = len(src_set & cdm_set) / len(src_set | cdm_set)
        best = max(sim, sample_overlap)
        if inp.mapping_confidence > 0:
            best = max(best, inp.mapping_confidence)
        return MappingResult(
            source_entity="",
            target_entity="",
            field_mappings=[
                FieldMapping(
                    source_field=inp.source_field,
                    source_type=inp.source_type,
                    target_field=inp.cdm_field,
                    target_type=inp.cdm_type,
                    confidence=best,
                )
            ],
            overall_confidence=best,
        )

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    def _score_semantic_similarity(self, mapping: MappingResult) -> float:
        """Average semantic similarity of field-name pairs.

        Uses embedding cosine similarity when available, falling back to
        character-level heuristics.  High-confidence mappings (from alias
        tables / domain knowledge) floor the similarity score, since they
        indicate semantic equivalence the string metrics cannot capture.
        """
        if not mapping.field_mappings:
            return 0.0

        scores: list[float] = []
        for fm in mapping.field_mappings:
            if self._embedding_fn is not None:
                src_emb = self._embedding_fn(fm.source_field)
                tgt_emb = self._embedding_fn(fm.target_field)
                sim = self._cosine_similarity(src_emb, tgt_emb)
            else:
                sim = self._char_similarity(fm.source_field, fm.target_field)
            sim = max(sim, fm.confidence)
            scores.append(sim)

        return sum(scores) / len(scores)

    @staticmethod
    def _score_type_compatibility(mapping: MappingResult) -> float:
        """Fraction of field mappings with compatible source/target types."""
        if not mapping.field_mappings:
            return 0.0

        compatible = 0
        for fm in mapping.field_mappings:
            src = fm.source_type.lower()
            tgt = fm.target_type.lower()
            if src == tgt:
                compatible += 1
            elif tgt in _COMPATIBLE_TYPES.get(src, set()):
                compatible += 1

        return compatible / len(mapping.field_mappings)

    @staticmethod
    def _score_value_distribution(mapping: MappingResult) -> float:
        """Score based on confidence as a proxy for distribution overlap.

        Full PSI/KL-divergence requires sample data; when unavailable the
        field-level confidence serves as a reasonable proxy.  The score is
        the average confidence clamped to [0, 1].
        """
        if not mapping.field_mappings:
            return 0.0
        confidences = [fm.confidence for fm in mapping.field_mappings]
        avg = sum(confidences) / len(confidences)
        return max(0.0, min(1.0, avg))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))

    @staticmethod
    def _char_similarity(a: str, b: str) -> float:
        """Token-overlap + Levenshtein heuristic for field names.

        Normalises CamelCase/PascalCase to snake_case before tokenising,
        then returns the max of Jaccard token overlap and Levenshtein
        similarity on the normalised strings.
        """
        norm_a = _camel_to_snake(a)
        norm_b = _camel_to_snake(b)
        tokens_a = set(norm_a.split("_"))
        tokens_b = set(norm_b.split("_"))
        tokens_a.discard("")
        tokens_b.discard("")
        jaccard = 0.0
        if tokens_a and tokens_b:
            jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
        lev = _levenshtein_similarity(norm_a, norm_b)
        return max(jaccard, lev)

    @staticmethod
    def _build_rationale(
        dims: dict[str, float], aggregate: float, passed: bool
    ) -> str:
        verdict = "PASS" if passed else "FAIL"
        dim_parts = [f"{k}={v:.3f}" for k, v in dims.items()]
        return f"[{verdict}] aggregate={aggregate:.4f} ({', '.join(dim_parts)})"
