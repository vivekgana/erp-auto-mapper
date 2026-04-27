"""ERP schema extractors — one per ERP system, unified metadata output."""

from erp_auto_mapper.core.extractors.base import (
    BaseERPExtractor,
    ERPConnectionConfig,
    ERPMetadata,
    ERPType,
    EntityMetadata,
    FieldMetadata,
    Relationship,
)
from erp_auto_mapper.core.extractors.dynamics import DynamicsExtractor
from erp_auto_mapper.core.extractors.epicor import EpicorExtractor
from erp_auto_mapper.core.extractors.infor import InforExtractor
from erp_auto_mapper.core.extractors.netsuite import NetSuiteExtractor
from erp_auto_mapper.core.extractors.oracle import OracleERPExtractor
from erp_auto_mapper.core.extractors.sage import SageExtractor
from erp_auto_mapper.core.extractors.sap import SAPExtractor
from erp_auto_mapper.core.extractors.workday import WorkdayExtractor

__all__ = [
    "BaseERPExtractor",
    "ERPConnectionConfig",
    "ERPMetadata",
    "ERPType",
    "EntityMetadata",
    "FieldMetadata",
    "Relationship",
    "DynamicsExtractor",
    "EpicorExtractor",
    "InforExtractor",
    "NetSuiteExtractor",
    "OracleERPExtractor",
    "SageExtractor",
    "SAPExtractor",
    "WorkdayExtractor",
]
