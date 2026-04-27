"""MapFieldsSkill — 3-pass ensemble mapping with feedback and reward priors."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from erp_auto_mapper.core.cdm.registry import CDMRegistry
from erp_auto_mapper.core.extractors.base import EntityMetadata, ERPMetadata, FieldMetadata
from erp_auto_mapper.core.feedback.reward_engine import RewardEngine
from erp_auto_mapper.core.feedback.store import FeedbackStore
from erp_auto_mapper.core.mapper.embedding_pass import EmbeddingMappingPass, MappingCandidate
from erp_auto_mapper.core.mapper.ensemble import MappingEnsemble, MappingResult
from erp_auto_mapper.core.mapper.graph_pass import GraphMappingPass
from erp_auto_mapper.core.mapper.llm_pass import LLMMappingPass, RefinedMapping
from erp_auto_mapper.core.orchestrator import EntityMappingOutput
from erp_auto_mapper.core.entity_hints import ENTITY_HINTS, token_overlap
from erp_auto_mapper.core.skills.base import SkillContext, SkillResult

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], Awaitable[str]]

_PYTHON_TYPE_MAP: dict[str, str] = {
    "<class 'str'>": "string",
    "<class 'int'>": "integer",
    "<class 'float'>": "float",
    "<class 'bool'>": "boolean",
    "<class 'decimal.Decimal'>": "decimal",
    "<class 'datetime.date'>": "date",
    "<class 'datetime.datetime'>": "datetime",
    "<class 'datetime.time'>": "time",
    "<class 'bytes'>": "binary",
}


def _normalize_cdm_type(raw: str | None) -> str:
    if not raw:
        return "string"
    if raw in _PYTHON_TYPE_MAP:
        return _PYTHON_TYPE_MAP[raw]
    low = raw.lower()
    if "none" in low and "|" in low:
        base = raw.split("|")[0].strip()
        return _normalize_cdm_type(base)
    if "enum" in low:
        return "string"
    if low.startswith("list[") or low.startswith("dict["):
        return "string"
    return "string"


class MapFieldsSkill:
    """Map source ERP fields to CDM targets using the 3-pass ensemble.

    Optionally integrates with FeedbackStore and RewardEngine to boost
    candidates based on prior corrections and accumulated rewards.
    """

    def __init__(
        self,
        feedback_store: FeedbackStore | None = None,
        reward_engine: RewardEngine | None = None,
        llm_callable: LLMCallable | None = None,
        embedding_provider: Any = None,
        top_k: int = 10,
        min_threshold: float = 0.0,
    ) -> None:
        self._feedback = feedback_store
        self._reward = reward_engine
        self._cdm = CDMRegistry()
        self._embedding_pass = EmbeddingMappingPass(
            embedding_provider=embedding_provider,
            top_k=top_k,
            min_threshold=min_threshold,
        )
        self._llm_pass = LLMMappingPass(llm_callable) if llm_callable else None
        self._graph_pass = GraphMappingPass()
        self._ensemble = MappingEnsemble()

    @property
    def name(self) -> str:
        return "map_fields"

    async def execute(self, context: SkillContext) -> SkillResult:
        metadata = context.metadata
        if metadata is None:
            return SkillResult(
                skill_name=self.name,
                status="failed",
                error="No ERPMetadata in context — run ExtractSkill first",
            )

        entity_pairs = self._match_entities(metadata)
        if not entity_pairs:
            return SkillResult(
                skill_name=self.name,
                status="failed",
                error="No entity matches found between source and CDM",
            )

        entity_mappings: list[EntityMappingOutput] = []
        for source_entity, cdm_name in entity_pairs:
            em = await self._map_entity(
                source_entity, cdm_name, metadata.entities, context.erp_type
            )
            entity_mappings.append(em)

        context.entity_mappings = entity_mappings
        total_mappings = sum(len(em.field_mappings) for em in entity_mappings)
        auto = sum(
            1
            for em in entity_mappings
            for fm in em.field_mappings
            if fm.get("band") == "auto"
        )

        return SkillResult(
            skill_name=self.name,
            output=entity_mappings,
            metrics={
                "entities_mapped": len(entity_mappings),
                "total_mappings": total_mappings,
                "auto_accepted": auto,
                "review_needed": total_mappings - auto,
            },
        )

    def _match_entities(
        self, metadata: ERPMetadata
    ) -> list[tuple[EntityMetadata, str]]:
        cdm_names = self._cdm.list_entities()
        pairs: list[tuple[EntityMetadata, str]] = []

        for entity in metadata.entities:
            normalized = entity.name.lower().replace(" ", "").replace("_", "")
            hint = ENTITY_HINTS.get(normalized)
            if hint and hint in cdm_names:
                pairs.append((entity, hint))
                continue

            best_name = ""
            best_score = 0.0
            for cdm_name in cdm_names:
                score = token_overlap(entity.name, cdm_name)
                if score > best_score:
                    best_score = score
                    best_name = cdm_name

            if best_score >= 0.2 and best_name:
                pairs.append((entity, best_name))

        return pairs

    async def _map_entity(
        self,
        source_entity: EntityMetadata,
        cdm_entity_name: str,
        all_source_entities: list[EntityMetadata],
        erp_type: str,
    ) -> EntityMappingOutput:
        candidates = self._embedding_pass.map_fields(
            source_entity.fields, cdm_entity_name
        )

        if self._feedback:
            for c in candidates:
                boost = self._feedback.compute_boost(
                    erp_type, c.source_field, c.cdm_field
                )
                c.score = max(0.0, min(1.0, c.score + boost))

        if self._reward:
            candidate_names = list({c.cdm_field for c in candidates})
            for source_field in {c.source_field for c in candidates}:
                boosts = self._reward.suggest_deterministic(
                    erp_type, source_field, candidate_names
                )
                for c in candidates:
                    if c.source_field == source_field:
                        b = boosts.get(c.cdm_field, 0.0)
                        c.score = max(0.0, min(1.0, c.score + b))

        if self._llm_pass is not None:
            best_per_field: dict[str, MappingCandidate] = {}
            for c in candidates:
                existing = best_per_field.get(c.source_field)
                if existing is None or c.score > existing.score:
                    best_per_field[c.source_field] = c

            refined: list[RefinedMapping] = []
            for candidate in best_per_field.values():
                source_meta = self._find_field(source_entity, candidate.source_field)
                cdm_meta = self._cdm_field_meta(cdm_entity_name, candidate.cdm_field)
                rm = await self._llm_pass.refine_mapping(candidate, source_meta, cdm_meta)
                refined.append(rm)
        else:
            refined = [
                RefinedMapping(
                    source_field=c.source_field,
                    cdm_field=c.cdm_field,
                    confidence=c.score,
                    method="embedding",
                    embedding_score=c.score,
                )
                for c in candidates
            ]

        boosted = self._graph_pass.boost_scores(
            refined, all_source_entities, [cdm_entity_name]
        )

        best_map: dict[str, RefinedMapping] = {}
        for m in boosted:
            prev = best_map.get(m.source_field)
            if prev is None or m.confidence > prev.confidence:
                best_map[m.source_field] = m

        field_mappings: list[dict[str, Any]] = []
        for m in best_map.values():
            band = MappingResult.classify_confidence(m.confidence)
            source_meta = self._find_field(source_entity, m.source_field)
            cdm_type = _normalize_cdm_type(self._cdm.get_field_type(cdm_entity_name, m.cdm_field))
            field_mappings.append({
                "source_field": m.source_field,
                "cdm_field": m.cdm_field,
                "confidence": round(m.confidence, 4),
                "band": band.value,
                "transform_expression": m.transform_expression,
                "rationale": m.rationale,
                "method": m.method,
                "embedding_score": m.embedding_score,
                "source_type": source_meta.type,
                "cdm_type": cdm_type,
            })

        field_mappings.sort(key=lambda fm: fm["confidence"], reverse=True)

        return EntityMappingOutput(
            source_entity=source_entity.name,
            cdm_entity=cdm_entity_name,
            field_mappings=field_mappings,
        )

    def _cdm_field_meta(self, entity_name: str, field_name: str) -> FieldMetadata:
        field_type = _normalize_cdm_type(self._cdm.get_field_type(entity_name, field_name))
        return FieldMetadata(name=field_name, type=field_type)

    @staticmethod
    def _find_field(entity: EntityMetadata, field_name: str) -> FieldMetadata:
        for f in entity.fields:
            if f.name == field_name:
                return f
        return FieldMetadata(name=field_name, type="string")
