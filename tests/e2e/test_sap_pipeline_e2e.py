"""E2E test — full SAP pipeline from CSV fixture through mapping and eval."""

import json
from pathlib import Path

import pytest

from erp_auto_mapper.core.extractors.base import EntityMetadata, ERPMetadata, ERPType, FieldMetadata
from erp_auto_mapper.core.ingest.file_reader import FileFormatReader
from erp_auto_mapper.core.ingest.schema_inferrer import SchemaInferrer
from erp_auto_mapper.core.orchestrator import ERPMappingOrchestrator, OrchestratorConfig

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_sap_csv_pipeline():
    reader = FileFormatReader()
    result = reader.read(FIXTURE_DIR / "sap_journal_entry.csv")
    assert result.row_count == 20

    inferrer = SchemaInferrer()
    inferred_fields = inferrer.infer_fields(result.rows)
    assert len(inferred_fields) == 10

    entity = EntityMetadata(name="BKPF", fields=inferred_fields)
    metadata = ERPMetadata(source=ERPType.SAP, entities=[entity])

    config = OrchestratorConfig(engagement_id="e2e-sap")
    orch = ERPMappingOrchestrator(config=config)
    output = await orch.run(metadata)

    assert len(output.entity_mappings) > 0
    em = output.entity_mappings[0]
    assert em.cdm_entity == "JournalEntry"
    assert len(em.field_mappings) > 0

    output_dict = output.model_dump()
    assert "entity_mappings" in output_dict


@pytest.mark.asyncio
async def test_oracle_json_pipeline():
    oracle_path = FIXTURE_DIR / "oracle_gl.json"
    records = json.loads(oracle_path.read_text())
    assert len(records) == 10

    fields = [FieldMetadata(name=k, type="string") for k in records[0].keys()]
    entity = EntityMetadata(name="GL_JE_LINES", fields=fields)
    metadata = ERPMetadata(source=ERPType.ORACLE, entities=[entity])

    config = OrchestratorConfig(engagement_id="e2e-oracle")
    orch = ERPMappingOrchestrator(config=config)
    output = await orch.run(metadata)

    assert len(output.entity_mappings) > 0
    assert len(output.entity_mappings[0].field_mappings) > 0
