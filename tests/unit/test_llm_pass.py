"""Unit tests for LLMMappingPass — refine_mapping with mock LLM."""

import pytest

from erp_auto_mapper.core.extractors.base import FieldMetadata
from erp_auto_mapper.core.mapper.embedding_pass import MappingCandidate
from erp_auto_mapper.core.mapper.llm_pass import LLMMappingPass, RefinedMapping


@pytest.mark.asyncio
async def test_llm_pass_with_mock(mock_llm_callable):
    llm_pass = LLMMappingPass(llm_callable=mock_llm_callable)
    candidate = MappingCandidate(source_field="BUKRS", cdm_field="company_code", score=0.8, method="alias")
    source_meta = FieldMetadata(name="BUKRS", type="string", description="Company Code")
    cdm_meta = FieldMetadata(name="company_code", type="string", description="Company code")
    refined = await llm_pass.refine_mapping(candidate, source_meta, cdm_meta)
    assert isinstance(refined, RefinedMapping)
    assert refined.source_field == "BUKRS"


@pytest.mark.asyncio
async def test_llm_pass_fallback_on_error():
    async def failing_llm(prompt: str) -> str:
        raise RuntimeError("LLM unavailable")

    llm_pass = LLMMappingPass(llm_callable=failing_llm)
    candidate = MappingCandidate(source_field="BUKRS", cdm_field="company_code", score=0.5, method="alias")
    source_meta = FieldMetadata(name="BUKRS", type="string")
    cdm_meta = FieldMetadata(name="company_code", type="string")
    refined = await llm_pass.refine_mapping(candidate, source_meta, cdm_meta)
    assert isinstance(refined, RefinedMapping)
