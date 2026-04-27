"""ERP Auto Mapper Core — pure-Python ERP-to-CDM mapping engine."""

from __future__ import annotations

from erp_auto_mapper.core.cdm.registry import CDMRegistry
from erp_auto_mapper.core.entity_hints import ENTITY_HINTS
from erp_auto_mapper.core.eval.business_rule_validator import BusinessRuleValidator
from erp_auto_mapper.core.eval.golden_set_evaluator import GoldenSetEvaluator
from erp_auto_mapper.core.eval.llm_judge import MappingLLMJudge
from erp_auto_mapper.core.eval.mapping_scorer import MappingInput, MappingScorer
from erp_auto_mapper.core.eval.regression_detector import RegressionDetector
from erp_auto_mapper.core.extractors.base import (
    BaseERPExtractor,
    EntityMetadata,
    ERPConnectionConfig,
    ERPMetadata,
    ERPType,
    FieldMetadata,
)
from erp_auto_mapper.core.feedback.reward_engine import RewardEngine
from erp_auto_mapper.core.feedback.store import FeedbackStore
from erp_auto_mapper.core.ingest.file_reader import FileFormatReader
from erp_auto_mapper.core.ingest.schema_inferrer import SchemaInferrer
from erp_auto_mapper.core.mapper.embedding_pass import EmbeddingMappingPass
from erp_auto_mapper.core.mapper.ensemble import ConfidenceBand, MappingEnsemble, MappingResult
from erp_auto_mapper.core.mapper.graph_pass import GraphMappingPass
from erp_auto_mapper.core.mapper.llm_pass import LLMMappingPass
from erp_auto_mapper.core.mapper.memory_store import MappingMemoryStore
from erp_auto_mapper.core.orchestrator import ERPMappingOrchestrator, MappingOutput, OrchestratorConfig
from erp_auto_mapper.core.skills.base import ETLPipeline, ETLSkill, SkillContext, SkillResult
from erp_auto_mapper.core.skills.map_fields_skill import MapFieldsSkill
from erp_auto_mapper.core.skills.validate_skill import ValidateQualitySkill
from erp_auto_mapper.core.transform.generator import TransformationGenerator

__all__ = [
    "BaseERPExtractor",
    "BusinessRuleValidator",
    "CDMRegistry",
    "ConfidenceBand",
    "EmbeddingMappingPass",
    "ENTITY_HINTS",
    "EntityMetadata",
    "ERPConnectionConfig",
    "ERPMappingOrchestrator",
    "ERPMetadata",
    "ERPType",
    "ETLPipeline",
    "ETLSkill",
    "FeedbackStore",
    "FieldMetadata",
    "FileFormatReader",
    "GoldenSetEvaluator",
    "GraphMappingPass",
    "LLMMappingPass",
    "MapFieldsSkill",
    "MappingEnsemble",
    "MappingInput",
    "MappingLLMJudge",
    "MappingMemoryStore",
    "MappingOutput",
    "MappingResult",
    "MappingScorer",
    "OrchestratorConfig",
    "RegressionDetector",
    "RewardEngine",
    "SchemaInferrer",
    "SkillContext",
    "SkillResult",
    "TransformationGenerator",
    "ValidateQualitySkill",
]
