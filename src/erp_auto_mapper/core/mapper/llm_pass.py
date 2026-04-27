"""LLM-based mapping refinement pass (Pass 2 of the AI Mapping Engine)."""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from erp_auto_mapper.core.extractors.base import FieldMetadata
from erp_auto_mapper.core.mapper.embedding_pass import MappingCandidate

logger = logging.getLogger(__name__)

LLM_CONFIDENCE_CAP: float = 0.70

LLMCallable = Callable[[str], Awaitable[str]]


class RefinedMapping(BaseModel):
    """Mapping enriched by the LLM with a transform expression and rationale."""

    source_field: str
    cdm_field: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    transform_expression: str = ""
    rationale: str = ""
    method: str = "llm"
    embedding_score: float = 0.0


class LLMMappingPass:
    """Second pass: LLM-assisted mapping refinement.

    llm_callable takes a single prompt string and returns a JSON string.
    """

    def __init__(self, llm_callable: LLMCallable) -> None:
        self._llm = llm_callable

    async def refine_mapping(
        self,
        candidate: MappingCandidate,
        source_meta: FieldMetadata,
        cdm_meta: FieldMetadata,
    ) -> RefinedMapping:
        """Refine a single candidate mapping via LLM."""
        prompt = (
            f"Assess this ERP-to-CDM field mapping.\n"
            f"Source: {source_meta.name} ({source_meta.type})"
            f"{' - ' + source_meta.description if source_meta.description else ''}\n"
            f"CDM: {cdm_meta.name} ({cdm_meta.type})"
            f"{' - ' + cdm_meta.description if cdm_meta.description else ''}\n"
            f"Embedding score: {candidate.score}\n"
            f'Respond with JSON: {{"cdm_field": "<str>", "confidence": <float>, '
            f'"transform_expression": "<str>", "rationale": "<str>"}}'
        )

        try:
            raw = await self._llm(prompt)
            data = json.loads(raw)
            raw_confidence = float(data.get("confidence", candidate.score))
            has_embedding_confirmation = candidate.score >= 0.5
            capped = raw_confidence if has_embedding_confirmation else min(raw_confidence, LLM_CONFIDENCE_CAP)
            return RefinedMapping(
                source_field=candidate.source_field,
                cdm_field=data.get("cdm_field", candidate.cdm_field) or candidate.cdm_field,
                confidence=round(capped, 4),
                transform_expression=data.get("transform_expression", "") or "",
                rationale=data.get("rationale", "") or "",
                method="llm",
                embedding_score=candidate.score,
            )
        except Exception:
            logger.warning("LLM refinement failed for %s -> %s", candidate.source_field, candidate.cdm_field)
            return RefinedMapping(
                source_field=candidate.source_field,
                cdm_field=candidate.cdm_field,
                confidence=min(candidate.score, 0.5),
                transform_expression="",
                rationale="LLM call failed.",
                method="llm_fallback",
                embedding_score=candidate.score,
            )
