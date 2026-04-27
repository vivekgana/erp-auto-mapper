"""ERP Mapping Orchestrator — end-to-end pipeline tying together the 5 pillars."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from erp_auto_mapper.core.cdm.registry import CDMRegistry
from erp_auto_mapper.core.eval.mapping_scorer import MappingInput, MappingScorer
from erp_auto_mapper.core.eval.golden_set_evaluator import GoldenSetEvaluator
from erp_auto_mapper.core.eval.regression_detector import (
    MappingEvalResult as RegMappingEvalResult,
    RegressionDetector,
)
from erp_auto_mapper.core.extractors.base import (
    BaseERPExtractor,
    EntityMetadata,
    ERPConnectionConfig,
    ERPMetadata,
    ERPType,
    FieldMetadata,
)
from erp_auto_mapper.core.mapper.embedding_pass import EmbeddingMappingPass, MappingCandidate
from erp_auto_mapper.core.mapper.ensemble import MappingEnsemble, MappingResult
from erp_auto_mapper.core.mapper.graph_pass import GraphMappingPass
from erp_auto_mapper.core.mapper.llm_pass import LLMMappingPass, RefinedMapping
from erp_auto_mapper.core.mapper.memory_store import MappingMemoryStore
from erp_auto_mapper.core.transform.generator import TransformationGenerator
from erp_auto_mapper.core.entity_hints import ENTITY_HINTS, token_overlap

logger = logging.getLogger(__name__)

LLMCallable = Callable[[str], Awaitable[str]]


class OrchestratorConfig(BaseModel):
    """Configuration for a single orchestrator run."""

    model_config = {"arbitrary_types_allowed": True}

    engagement_id: str
    erp_connection: ERPConnectionConfig | None = None
    output_dir: str = "output"
    llm_callable: Any = None
    embedding_provider: Any = None
    top_k: int = 10
    min_threshold: float = 0.0
    skip_eval: bool = False
    golden_set: list[dict[str, str]] | None = None
    baseline_id: str | None = None
    delta_client: Any = None
    source_files: list[str] | None = None
    source_erp_type: str = "sap"
    bronze_ingest: bool = False


class EntityMappingOutput(BaseModel):
    """Complete mapping result for one source entity to one CDM entity."""

    source_entity: str
    cdm_entity: str
    field_mappings: list[dict[str, Any]] = Field(default_factory=list)


class MappingOutput(BaseModel):
    """Complete output from an orchestrator run."""

    engagement_id: str
    erp_type: str
    erp_version: str = ""
    timestamp: str = ""
    entity_count: int = 0
    field_count: int = 0
    entity_mappings: list[EntityMappingOutput] = Field(default_factory=list)
    sql: dict[str, str] = Field(default_factory=dict)
    eval_report: dict[str, Any] | None = None


class RunManifest(BaseModel):
    """Metadata manifest for a single orchestrator run."""

    engagement_id: str
    erp_type: str
    erp_version: str = ""
    timestamp: str = ""
    entity_count: int = 0
    field_count: int = 0
    total_mappings: int = 0
    auto_count: int = 0
    review_count: int = 0
    manual_count: int = 0
    overall_confidence: float = 0.0
    eval_aggregate: float | None = None
    duration_seconds: float = 0.0


class ERPMappingOrchestrator:
    """End-to-end orchestrator for the 5-pillar ERP auto-mapping system.

    Pipeline: extract → match entities → map fields → transform → eval → persist
    """

    def __init__(self, config: OrchestratorConfig) -> None:
        self._config = config
        self._cdm = CDMRegistry()
        self._embedding_pass = EmbeddingMappingPass(
            embedding_provider=config.embedding_provider,
            top_k=config.top_k,
            min_threshold=config.min_threshold,
        )
        self._llm_pass: LLMMappingPass | None = (
            LLMMappingPass(config.llm_callable) if config.llm_callable else None
        )
        self._graph_pass = GraphMappingPass()
        self._ensemble = MappingEnsemble()
        self._transform_gen = TransformationGenerator()
        self._memory = MappingMemoryStore()

    async def run(self, metadata: ERPMetadata | None = None) -> MappingOutput:
        """Execute the full pipeline."""
        start = time.time()
        ts = datetime.now(timezone.utc).isoformat()

        if metadata is None:
            if self._config.source_files:
                metadata = await self._extract_from_files()
            else:
                metadata = await self._extract()

        logger.info(
            "Orchestrator started: erp=%s, entities=%d, fields=%d",
            metadata.source.value,
            len(metadata.entities),
            metadata.field_count(),
        )

        entity_pairs = self._match_entities(metadata)
        logger.info("Matched %d entity pairs", len(entity_pairs))

        entity_mappings: list[EntityMappingOutput] = []
        for source_entity, cdm_name in entity_pairs:
            em = await self._map_entity(source_entity, cdm_name, metadata.entities)
            entity_mappings.append(em)

        sql = self._generate_transforms(entity_mappings)

        eval_report: dict[str, Any] | None = None
        if not self._config.skip_eval:
            eval_report = await self._evaluate(entity_mappings, metadata)

        output = MappingOutput(
            engagement_id=self._config.engagement_id,
            erp_type=metadata.source.value,
            erp_version=metadata.source_version,
            timestamp=ts,
            entity_count=len(metadata.entities),
            field_count=metadata.field_count(),
            entity_mappings=entity_mappings,
            sql=sql,
            eval_report=eval_report,
        )

        duration = time.time() - start
        all_mappings = [fm for em in entity_mappings for fm in em.field_mappings]
        auto = sum(1 for fm in all_mappings if fm.get("band") == "auto")
        review = sum(1 for fm in all_mappings if fm.get("band") == "review")
        manual = sum(1 for fm in all_mappings if fm.get("band") == "manual")
        avg_conf = (
            sum(fm.get("confidence", 0) for fm in all_mappings) / len(all_mappings)
            if all_mappings
            else 0.0
        )

        manifest = RunManifest(
            engagement_id=self._config.engagement_id,
            erp_type=metadata.source.value,
            erp_version=metadata.source_version,
            timestamp=ts,
            entity_count=len(metadata.entities),
            field_count=metadata.field_count(),
            total_mappings=len(all_mappings),
            auto_count=auto,
            review_count=review,
            manual_count=manual,
            overall_confidence=round(avg_conf, 4),
            eval_aggregate=(
                eval_report.get("aggregate") if eval_report else None
            ),
            duration_seconds=round(duration, 2),
        )

        self._persist_output(output, manifest)

        if self._config.delta_client:
            from erp_auto_mapper.core.delta_sink import DeltaSink

            sink = DeltaSink(self._config.delta_client)
            await sink.ensure_tables()
            await sink.write(output, manifest)

        if self._config.bronze_ingest and self._config.delta_client and self._config.source_files:
            from erp_auto_mapper.core.ingest.bronze_writer import BronzeWriter

            bronze = BronzeWriter(self._config.delta_client)
            for fp in self._config.source_files:
                await bronze.ingest_file(fp)

        confirmed = [
            {"source": fm["source_field"], "cdm": fm["cdm_field"]}
            for fm in all_mappings
            if fm.get("band") == "auto"
        ]
        if confirmed:
            self._memory.store(self._config.engagement_id, confirmed)

        logger.info(
            "Orchestrator finished in %.1fs: %d mappings (auto=%d, review=%d, manual=%d)",
            duration, len(all_mappings), auto, review, manual,
        )

        return output

    async def _extract(self) -> ERPMetadata:
        """Pillar 1: dispatch to the correct extractor."""
        from erp_auto_mapper.core.extractors.dynamics import DynamicsExtractor
        from erp_auto_mapper.core.extractors.epicor import EpicorExtractor
        from erp_auto_mapper.core.extractors.infor import InforExtractor
        from erp_auto_mapper.core.extractors.netsuite import NetSuiteExtractor
        from erp_auto_mapper.core.extractors.oracle import OracleERPExtractor
        from erp_auto_mapper.core.extractors.sage import SageExtractor
        from erp_auto_mapper.core.extractors.sap import SAPExtractor
        from erp_auto_mapper.core.extractors.workday import WorkdayExtractor

        extractor_map: dict[ERPType, type[BaseERPExtractor]] = {
            ERPType.SAP: SAPExtractor,
            ERPType.ORACLE: OracleERPExtractor,
            ERPType.DYNAMICS: DynamicsExtractor,
            ERPType.NETSUITE: NetSuiteExtractor,
            ERPType.WORKDAY: WorkdayExtractor,
            ERPType.INFOR: InforExtractor,
            ERPType.EPICOR: EpicorExtractor,
            ERPType.SAGE: SageExtractor,
        }

        if self._config.erp_connection is None:
            raise ValueError("erp_connection is required when metadata is not provided")

        cls = extractor_map.get(self._config.erp_connection.erp_type)
        if cls is None:
            raise ValueError(f"No extractor for ERP type: {self._config.erp_connection.erp_type}")

        extractor = cls(self._config.erp_connection)
        return await extractor.extract()

    async def _extract_from_files(self) -> ERPMetadata:
        """Extract ERPMetadata from local files using FileBasedExtractor."""
        from erp_auto_mapper.core.extractors.file_extractor import FileBasedExtractor

        erp_type_map = {v.value: v for v in ERPType}
        erp_type = erp_type_map.get(self._config.source_erp_type, ERPType.SAP)

        extractor = FileBasedExtractor(
            source_files=list(self._config.source_files or []),
            erp_type=erp_type,
        )
        return await extractor.extract()

    def _match_entities(
        self, metadata: ERPMetadata
    ) -> list[tuple[EntityMetadata, str]]:
        """Match source ERP entities to CDM entities."""
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
                if entity.description:
                    desc_score = token_overlap(entity.description, cdm_name)
                    score = max(score, desc_score)
                if score > best_score:
                    best_score = score
                    best_name = cdm_name

            if best_score >= 0.2 and best_name:
                pairs.append((entity, best_name))
            else:
                logger.warning(
                    "No CDM match for source entity '%s' (best: %s @ %.2f)",
                    entity.name, best_name, best_score,
                )

        return pairs

    async def _map_entity(
        self,
        source_entity: EntityMetadata,
        cdm_entity_name: str,
        all_source_entities: list[EntityMetadata],
    ) -> EntityMappingOutput:
        """Pillar 3: run 3-pass mapping for one entity pair."""
        candidates = self._embedding_pass.map_fields(
            source_entity.fields, cdm_entity_name
        )

        if self._llm_pass is not None:
            best_per_field: dict[str, MappingCandidate] = {}
            for c in candidates:
                existing = best_per_field.get(c.source_field)
                if existing is None or c.score > existing.score:
                    best_per_field[c.source_field] = c

            refined: list[RefinedMapping] = []
            for candidate in best_per_field.values():
                source_meta = self._find_field_meta(source_entity, candidate.source_field)
                cdm_meta = self._cdm_field_to_metadata(cdm_entity_name, candidate.cdm_field)
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
            field_mappings.append({
                "source_field": m.source_field,
                "cdm_field": m.cdm_field,
                "confidence": round(m.confidence, 4),
                "band": band.value,
                "transform_expression": m.transform_expression,
                "rationale": m.rationale,
                "method": m.method,
                "embedding_score": m.embedding_score,
            })

        field_mappings.sort(key=lambda fm: fm["confidence"], reverse=True)

        return EntityMappingOutput(
            source_entity=source_entity.name,
            cdm_entity=cdm_entity_name,
            field_mappings=field_mappings,
        )

    def _generate_transforms(
        self, entity_mappings: list[EntityMappingOutput]
    ) -> dict[str, str]:
        """Pillar 4: generate dbt-style SQL from confirmed mappings."""
        staging_parts: list[str] = []
        transform_parts: list[str] = []
        mart_parts: list[str] = []

        for em in entity_mappings:
            mapping_dict: dict[str, Any] = {
                "source_table": em.source_entity,
                "cdm_entity": em.cdm_entity,
                "fields": [
                    {
                        "source": fm["source_field"],
                        "target": fm["cdm_field"],
                        "transform": fm.get("transform_expression", "direct") or "direct",
                    }
                    for fm in em.field_mappings
                ],
            }
            output = self._transform_gen.generate_full(mapping_dict)
            staging_parts.append(output.sql_staging)
            transform_parts.append(output.sql_transform)
            mart_parts.append(output.sql_mart)

        return {
            "staging": "\n\n".join(staging_parts),
            "transform": "\n\n".join(transform_parts),
            "mart": "\n\n".join(mart_parts),
        }

    async def _evaluate(
        self,
        entity_mappings: list[EntityMappingOutput],
        metadata: ERPMetadata,
    ) -> dict[str, Any]:
        """Pillar 5: run the evaluation scorecard."""
        scorer = MappingScorer()
        entity_scores: list[dict[str, Any]] = []

        for em in entity_mappings:
            for fm in em.field_mappings:
                inp = MappingInput(
                    source_field=fm["source_field"],
                    cdm_field=fm["cdm_field"],
                    source_type=self._get_source_type(metadata, em.source_entity, fm["source_field"]),
                    cdm_type=self._cdm.get_field_type(em.cdm_entity, fm["cdm_field"]) or "",
                )
                result = scorer.score(inp)
                entity_scores.append({
                    "source_field": fm["source_field"],
                    "cdm_field": fm["cdm_field"],
                    "per_dimension": result.per_dimension,
                    "aggregate": result.aggregate,
                    "passed": result.passed,
                })

        avg_aggregate = (
            sum(s["aggregate"] for s in entity_scores) / len(entity_scores)
            if entity_scores
            else 0.0
        )

        report: dict[str, Any] = {
            "field_scores": entity_scores,
            "aggregate": round(avg_aggregate, 4),
            "total_fields": len(entity_scores),
            "fields_passed": sum(1 for s in entity_scores if s["passed"]),
        }

        if self._config.golden_set:
            all_predicted = [
                {"source": fm["source_field"], "cdm": fm["cdm_field"]}
                for em in entity_mappings
                for fm in em.field_mappings
            ]
            gs_eval = GoldenSetEvaluator()
            gs_result = gs_eval.evaluate(
                all_predicted, self._config.golden_set, metadata.source
            )
            report["golden_set"] = gs_result.model_dump()

        if self._config.baseline_id:
            detector = RegressionDetector()
            current = RegMappingEvalResult(
                per_dimension={"aggregate": avg_aggregate},
                aggregate=avg_aggregate,
                passed=avg_aggregate >= 0.85,
            )
            reg_result = detector.detect(current, self._config.baseline_id)
            report["regression"] = reg_result.model_dump()

        return report

    def _persist_output(self, output: MappingOutput, manifest: RunManifest) -> Path:
        """Write all output files to disk."""
        base = Path(self._config.output_dir) / self._config.engagement_id
        sql_dir = base / "sql"
        sql_dir.mkdir(parents=True, exist_ok=True)

        (base / "mapping_results.json").write_text(
            output.model_dump_json(indent=2), encoding="utf-8"
        )
        (base / "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )

        if output.eval_report:
            (base / "eval_report.json").write_text(
                json.dumps(output.eval_report, indent=2, default=str),
                encoding="utf-8",
            )

        for layer in ("staging", "transform", "mart"):
            sql_content = output.sql.get(layer, "")
            if sql_content:
                (sql_dir / f"{layer}.sql").write_text(sql_content, encoding="utf-8")

        logger.info("Output written to %s", base)
        return base

    def _cdm_field_to_metadata(self, entity_name: str, field_name: str) -> FieldMetadata:
        """Synthesize a FieldMetadata for a CDM field from the registry."""
        field_type = self._cdm.get_field_type(entity_name, field_name) or "string"
        embeddings = self._cdm.get_field_embeddings(entity_name)
        description = ""
        for fname, embed_text in embeddings:
            if fname == field_name:
                description = embed_text
                break
        return FieldMetadata(
            name=field_name,
            type=field_type,
            description=description,
        )

    @staticmethod
    def _find_field_meta(entity: EntityMetadata, field_name: str) -> FieldMetadata:
        for f in entity.fields:
            if f.name == field_name:
                return f
        return FieldMetadata(name=field_name, type="string")

    @staticmethod
    def _get_source_type(
        metadata: ERPMetadata, entity_name: str, field_name: str
    ) -> str:
        for entity in metadata.entities:
            if entity.name == entity_name:
                for f in entity.fields:
                    if f.name == field_name:
                        return f.type
        return ""
