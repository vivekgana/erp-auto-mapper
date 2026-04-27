"""Graph-based structural similarity pass (Pass 3 of the AI Mapping Engine)."""

from __future__ import annotations

import logging
from collections import defaultdict

from erp_auto_mapper.core.extractors.base import EntityMetadata
from erp_auto_mapper.core.mapper.llm_pass import RefinedMapping

logger = logging.getLogger(__name__)

_MAX_STRUCTURAL_BOOST: float = 0.10


class GraphMappingPass:
    """Third pass: structural graph-based confidence boosting."""

    def __init__(self) -> None:
        pass

    def boost_scores(
        self,
        mappings: list[RefinedMapping],
        source_entities: list[EntityMetadata],
        cdm_entities: list[str],
    ) -> list[RefinedMapping]:
        """Boost mapping scores based on graph-structural similarity."""
        if not mappings or not source_entities:
            return mappings

        adjacency: dict[str, set[str]] = defaultdict(set)
        for entity in source_entities:
            for rel in entity.relationships:
                adjacency[rel.source_entity].add(rel.target_entity)
                adjacency[rel.target_entity].add(rel.source_entity)

        source_field_to_entity: dict[str, str] = {}
        for entity in source_entities:
            for f in entity.fields:
                source_field_to_entity[f.name] = entity.name

        boosted: list[RefinedMapping] = []
        for m in mappings:
            src_entity = source_field_to_entity.get(m.source_field, "")
            neighbors = adjacency.get(src_entity, set())
            boost = 0.0
            if neighbors:
                mapped_neighbors = sum(
                    1 for other_m in mappings
                    if other_m.source_field != m.source_field
                    and source_field_to_entity.get(other_m.source_field, "") in neighbors
                    and other_m.confidence > 0.5
                )
                if mapped_neighbors > 0:
                    boost = min(
                        (mapped_neighbors / len(neighbors)) * _MAX_STRUCTURAL_BOOST,
                        _MAX_STRUCTURAL_BOOST,
                    )

            new_conf = min(m.confidence + boost, 1.0)
            boosted.append(m.model_copy(update={"confidence": round(new_conf, 4)}))

        return boosted
