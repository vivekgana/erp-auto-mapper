"""Base ERP extractor with unified metadata envelope."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ERPType(str, Enum):
    SAP = "sap"
    ORACLE = "oracle"
    DYNAMICS = "dynamics"
    NETSUITE = "netsuite"
    WORKDAY = "workday"
    INFOR = "infor"
    EPICOR = "epicor"
    SAGE = "sage"


class FieldMetadata(BaseModel):
    name: str
    type: str
    nullable: bool = True
    fk_ref: str | None = None
    enum_values: list[str] = Field(default_factory=list)
    description: str = ""
    sample_values: list[Any] = Field(default_factory=list)
    is_key: bool = False
    max_length: int | None = None


class Relationship(BaseModel):
    source_entity: str
    source_field: str
    target_entity: str
    target_field: str
    cardinality: str = "many-to-one"


class EntityMetadata(BaseModel):
    name: str
    description: str = ""
    fields: list[FieldMetadata] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)


class ERPMetadata(BaseModel):
    source: ERPType
    source_version: str = ""
    extraction_timestamp: str = ""
    entities: list[EntityMetadata] = Field(default_factory=list)
    raw_config: dict[str, Any] = Field(default_factory=dict)

    def field_count(self) -> int:
        return sum(len(e.fields) for e in self.entities)

    def entity_names(self) -> list[str]:
        return [e.name for e in self.entities]


class ERPConnectionConfig(BaseModel):
    erp_type: ERPType
    base_url: str
    auth_method: str = "oauth2"
    credentials_secret_scope: str = ""
    timeout_seconds: int = 30
    max_retries: int = 3
    rate_limit_per_second: float = 5.0
    extra: dict[str, Any] = Field(default_factory=dict)


class BaseERPExtractor(ABC):
    """Abstract base for all ERP schema extractors."""

    def __init__(self, config: ERPConnectionConfig) -> None:
        self.config = config

    @property
    @abstractmethod
    def erp_type(self) -> ERPType: ...

    @abstractmethod
    async def extract(self) -> ERPMetadata:
        """Extract schema metadata from the ERP system."""
        ...

    @abstractmethod
    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        """Extract sample values for specific fields."""
        ...

    async def health_check(self) -> bool:
        """Verify connectivity to the ERP system."""
        return True

    def _normalize_type(self, native_type: str) -> str:
        """Normalize ERP-native types to standard type names."""
        type_map = {
            "CHAR": "string",
            "VARCHAR": "string",
            "VARCHAR2": "string",
            "NVARCHAR": "string",
            "STRING": "string",
            "INT": "integer",
            "INTEGER": "integer",
            "INT32": "integer",
            "INT64": "long",
            "BIGINT": "long",
            "DECIMAL": "decimal",
            "DEC": "decimal",
            "FLOAT": "float",
            "DOUBLE": "double",
            "BOOLEAN": "boolean",
            "BOOL": "boolean",
            "DATE": "date",
            "DATETIME": "datetime",
            "TIMESTAMP": "datetime",
            "DATS": "date",
            "TIMS": "time",
            "NUMC": "string",
        }
        return type_map.get(native_type.upper(), "string")
