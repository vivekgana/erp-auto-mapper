"""ERP Auto Mapper — AI-powered ERP-to-CDM field mapping engine."""

__version__ = "0.1.0"

from erp_auto_mapper.core import (
    CDMRegistry,
    ConfidenceBand,
    EmbeddingMappingPass,
    ERPMappingOrchestrator,
    ERPMetadata,
    ERPType,
    ETLPipeline,
    FeedbackStore,
    GoldenSetEvaluator,
    MapFieldsSkill,
    MappingOutput,
    MappingResult,
    MappingScorer,
    OrchestratorConfig,
    RegressionDetector,
    RewardEngine,
    SchemaInferrer,
    ValidateQualitySkill,
)

__all__ = [
    "__version__",
    "CDMRegistry",
    "ConfidenceBand",
    "EmbeddingMappingPass",
    "ERPMappingOrchestrator",
    "ERPMetadata",
    "ERPType",
    "ETLPipeline",
    "FeedbackStore",
    "GoldenSetEvaluator",
    "MapFieldsSkill",
    "MappingOutput",
    "MappingResult",
    "MappingScorer",
    "OrchestratorConfig",
    "RegressionDetector",
    "RewardEngine",
    "SchemaInferrer",
    "ValidateQualitySkill",
]
