"""CDM Registry — versioned schema catalog with field-embedding helpers.

The registry stores all CDM entity schemas and provides look-ups used by the
AI Mapping Engine to compare source fields against canonical definitions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass


from erp_auto_mapper.core.cdm.entities import ALL_CDM_ENTITIES, CDMBase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _RegistryEntry:
    """Internal bookkeeping for a single registered entity version."""

    name: str
    schema_class: type[CDMBase]
    version: str


@dataclass
class HierarchyBridge:
    """A single parent-child pair in a flattened hierarchy."""

    parent_id: str | None
    child_id: str
    level: int


class CDMRegistry:
    """Versioned catalog of CDM entity schemas.

    Supports multiple versions per entity name so that backward-compatible
    schema evolution is possible without breaking existing mappings.
    """

    def __init__(self) -> None:
        # entity_name -> list of _RegistryEntry sorted by version ascending
        self._store: dict[str, list[_RegistryEntry]] = {}
        self._bootstrap_defaults()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_entity(
        self,
        name: str,
        schema_class: type[CDMBase],
        version: str | int = "1",
    ) -> None:
        """Register (or re-register) a CDM entity schema at a given version."""
        ver = str(version)
        entry = _RegistryEntry(name=name, schema_class=schema_class, version=ver)
        bucket = self._store.setdefault(name, [])

        for idx, existing in enumerate(bucket):
            if existing.version == ver:
                bucket[idx] = entry
                logger.info("Replaced CDM entity %s v%s", name, ver)
                return

        bucket.append(entry)
        bucket.sort(key=lambda e: e.version)
        logger.info("Registered CDM entity %s v%s", name, ver)

    def get_entity(
        self, name: str, version: str | int | None = None
    ) -> type[CDMBase] | None:
        """Return the schema class for *name*.  Latest version when *version* is ``None``."""
        bucket = self._store.get(name)
        if not bucket:
            return None
        if version is None:
            return bucket[-1].schema_class
        ver = str(version)
        for entry in bucket:
            if entry.version == ver:
                return entry.schema_class
        return None

    def get_field_embeddings(self, entity_name: str) -> list[tuple[str, str]]:
        """Return ``(field_name, embedding_text)`` pairs for the latest version.

        The *embedding_text* concatenates the field name, its type annotation,
        and any description found in the Pydantic ``Field`` metadata so that
        semantic-similarity search has rich context.
        """
        schema_cls = self.get_entity(entity_name)
        if schema_cls is None:
            return []

        result: list[tuple[str, str]] = []
        for field_name, field_info in schema_cls.model_fields.items():
            parts: list[str] = [field_name]
            annotation = field_info.annotation
            if annotation is not None:
                parts.append(str(annotation))
            if field_info.description:
                parts.append(field_info.description)
            result.append((field_name, " | ".join(parts)))
        return result

    def list_entities(self) -> list[str]:
        """Return sorted list of all registered entity names."""
        return sorted(self._store.keys())

    def get_hierarchy_bridge(self, entity_name: str) -> list[HierarchyBridge]:
        """Return flattened parent-child pairs for hierarchical entities.

        Only meaningful for entities that contain a ``parent_id`` field
        (Account, CostCenter, Organization).  Returns an empty list for
        non-hierarchical entities.
        """
        schema_cls = self.get_entity(entity_name)
        if schema_cls is None:
            return []

        if "parent_id" not in schema_cls.model_fields:
            return []

        # Return a template bridge showing the hierarchy structure exists.
        # Actual population happens at mapping time with real data.
        return [
            HierarchyBridge(parent_id=None, child_id="<root>", level=0),
        ]

    def get_all_field_names(self, entity_name: str) -> list[str]:
        """Return all field names for *entity_name* (latest version)."""
        schema_cls = self.get_entity(entity_name)
        if schema_cls is None:
            return []
        return list(schema_cls.model_fields.keys())

    def get_field_type(self, entity_name: str, field_name: str) -> str | None:
        """Return the string representation of a field's type annotation."""
        schema_cls = self.get_entity(entity_name)
        if schema_cls is None:
            return None
        field_info = schema_cls.model_fields.get(field_name)
        if field_info is None:
            return None
        annotation = field_info.annotation
        return str(annotation) if annotation is not None else None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _bootstrap_defaults(self) -> None:
        """Register all built-in CDM entities at version 1."""
        for name, cls in ALL_CDM_ENTITIES.items():
            self.register_entity(name, cls, version=1)
