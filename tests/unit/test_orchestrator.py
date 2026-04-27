"""Unit tests for ERPMappingOrchestrator — full pipeline."""

import pytest

from erp_auto_mapper.core.extractors.base import EntityMetadata, ERPMetadata, ERPType, FieldMetadata
from erp_auto_mapper.core.orchestrator import ERPMappingOrchestrator, OrchestratorConfig


@pytest.mark.asyncio
async def test_orchestrator_maps_sap(sap_metadata: ERPMetadata):
    config = OrchestratorConfig(engagement_id="test-001")
    orch = ERPMappingOrchestrator(config=config)
    result = await orch.run(sap_metadata)
    assert len(result.entity_mappings) > 0
    em = result.entity_mappings[0]
    assert em.cdm_entity == "JournalEntry"
    assert len(em.field_mappings) > 0


@pytest.mark.asyncio
async def test_orchestrator_empty_metadata():
    config = OrchestratorConfig(engagement_id="test-empty")
    orch = ERPMappingOrchestrator(config=config)
    metadata = ERPMetadata(source=ERPType.SAP, entities=[])
    result = await orch.run(metadata)
    assert result.entity_mappings == []


@pytest.mark.asyncio
async def test_orchestrator_single_field():
    config = OrchestratorConfig(engagement_id="test-single")
    orch = ERPMappingOrchestrator(config=config)
    metadata = ERPMetadata(
        source=ERPType.SAP,
        entities=[EntityMetadata(name="BKPF", fields=[FieldMetadata(name="BUKRS", type="string")])],
    )
    result = await orch.run(metadata)
    assert len(result.entity_mappings) == 1
