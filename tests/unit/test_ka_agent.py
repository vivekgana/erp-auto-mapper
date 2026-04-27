"""Tests for Knowledge Assistant agent."""

import json

from erp_auto_mapper.ka.agent import ERPKnowledgeAssistant, TOOL_DEFINITIONS, SKILL_MAP


class TestERPKnowledgeAssistant:
    def test_get_tools_returns_all_7(self):
        agent = ERPKnowledgeAssistant()
        tools = agent.get_tools()
        assert len(tools) == 7

    def test_tool_definitions_have_required_fields(self):
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool

    def test_skill_map_matches_definitions(self):
        tool_names = {t["name"] for t in TOOL_DEFINITIONS}
        skill_names = set(SKILL_MAP.keys())
        assert tool_names == skill_names

    def test_call_tool_lookup_alias(self):
        agent = ERPKnowledgeAssistant()
        result = agent.call_tool("lookup_alias", {"source_field": "company_code"})
        assert result["found"] is True
        assert result["cdm_field"] == "company_code"

    def test_call_tool_list_entities(self):
        agent = ERPKnowledgeAssistant()
        result = agent.call_tool("list_cdm_entities", {})
        assert len(result) == 10

    def test_call_tool_unknown_returns_error(self):
        agent = ERPKnowledgeAssistant()
        result = agent.call_tool("nonexistent_tool", {})
        assert "error" in result

    def test_predict_returns_tools_and_system_prompt(self):
        agent = ERPKnowledgeAssistant()
        response = agent.predict({
            "messages": [{"role": "user", "content": "What entities exist?"}]
        })
        assert "tools" in response
        assert "system_prompt" in response
        assert len(response["tools"]) == 7

    def test_predict_tool_call_dispatches(self):
        agent = ERPKnowledgeAssistant()
        response = agent.predict({
            "tool_call": {
                "name": "resolve_entity",
                "arguments": {"erp_table_name": "BKPF"},
            }
        })
        assert "tool_result" in response
        assert response["tool_result"]["cdm_entity"] == "JournalEntry"

    def test_predict_tool_call_with_string_arguments(self):
        agent = ERPKnowledgeAssistant()
        response = agent.predict({
            "tool_call": {
                "name": "lookup_alias",
                "arguments": json.dumps({"source_field": "fiscal_year"}),
            }
        })
        assert response["tool_result"]["found"] is True
