"""Knowledge Assistant agent — mlflow.pyfunc model wrapping ERP mapping skills as tools."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from erp_auto_mapper.ka.config import KAConfig
from erp_auto_mapper.ka import skills

logger = logging.getLogger(__name__)

SKILL_REGISTRY: list[Callable[..., Any]] = [
    skills.search_cdm_fields,
    skills.lookup_alias,
    skills.resolve_entity,
    skills.run_mapping,
    skills.get_historical_mappings,
    skills.list_cdm_entities,
    skills.get_entity_schema,
]

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_cdm_fields",
        "description": "Search the CDM field catalog using semantic similarity. Use when the user asks about CDM fields, what fields exist, or what a source field maps to.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language or field name to search for"},
                "entity_filter": {"type": "string", "description": "Optional CDM entity name to restrict results"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "lookup_alias",
        "description": "Check the ERP field alias table for a direct CDM mapping. Use when the user provides a specific ERP field name and wants an instant lookup.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_field": {"type": "string", "description": "ERP field name to look up"},
            },
            "required": ["source_field"],
        },
    },
    {
        "name": "resolve_entity",
        "description": "Resolve an ERP table name to its CDM entity. Use when the user asks which CDM entity an ERP table belongs to.",
        "parameters": {
            "type": "object",
            "properties": {
                "erp_table_name": {"type": "string", "description": "Raw ERP table name (e.g. BKPF, GL_JOURNALS)"},
            },
            "required": ["erp_table_name"],
        },
    },
    {
        "name": "run_mapping",
        "description": "Run the full 3-pass AI mapping for a set of ERP source fields against the CDM. Use when the user wants to map specific fields.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                    "description": "List of source field definitions",
                },
                "erp_type": {"type": "string", "description": "ERP system (sap, oracle, dynamics, netsuite, workday, infor, epicor, sage)"},
                "entity_name": {"type": "string", "description": "Source entity/table name"},
                "engagement_id": {"type": "string", "description": "Optional run identifier"},
            },
            "required": ["source_fields", "erp_type", "entity_name"],
        },
    },
    {
        "name": "get_historical_mappings",
        "description": "Query historical mapping results from the Delta table. Use when the user asks about past mapping runs or wants to see how a field was mapped previously.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_field": {"type": "string", "description": "ERP field name to look up"},
                "erp_type": {"type": "string", "description": "Optional ERP system filter"},
                "limit": {"type": "integer", "description": "Max rows to return (default 10)"},
            },
            "required": ["source_field"],
        },
    },
    {
        "name": "list_cdm_entities",
        "description": "List all CDM entities in the registry. Use when the user asks what entities are available or wants an overview of the CDM.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_entity_schema",
        "description": "Return the full field list and types for a CDM entity. Use when the user asks about the schema or fields of a specific CDM entity.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "CDM entity name (e.g. JournalEntry, Account)"},
            },
            "required": ["entity_name"],
        },
    },
]

SKILL_MAP: dict[str, Callable[..., Any]] = {fn.__name__: fn for fn in SKILL_REGISTRY}

SYSTEM_PROMPT = """\
You are the ERP Auto Mapper Knowledge Assistant — an AI expert on mapping ERP system \
schemas to a 10-entity Canonical Data Model (CDM) for financial audit.

You help users:
- Find which CDM fields or entities correspond to their ERP fields/tables
- Run AI-powered field mappings with confidence scoring
- Explore the CDM schema and understand field definitions
- Look up historical mapping results from past engagements

Always use the available tools to ground your answers in data. When mapping fields, \
explain the confidence scores and bands (AUTO >= 0.85, REVIEW >= 0.50, MANUAL < 0.50). \
Be concise and factual.\
"""


class ERPKnowledgeAssistant:
    """Databricks AI Agent wrapping ERP mapping skills as tools.

    Can be used standalone or logged as an mlflow.pyfunc model.
    """

    def __init__(self, config: KAConfig | None = None) -> None:
        self._config = config or KAConfig()

    def get_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions for the agent framework."""
        return TOOL_DEFINITIONS

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a skill by name with the given arguments."""
        fn = SKILL_MAP.get(tool_name)
        if fn is None:
            return {"error": f"Unknown tool: {tool_name}"}

        if tool_name in ("search_cdm_fields", "get_historical_mappings"):
            arguments["config"] = self._config

        try:
            return fn(**arguments)
        except Exception as exc:
            logger.exception("Tool %s failed", tool_name)
            return {"error": str(exc)}

    def predict(self, model_input: dict[str, Any]) -> dict[str, Any]:
        """Agent conversation endpoint.

        Accepts {"messages": [{"role": str, "content": str}, ...]} and returns
        {"messages": [...], "tools": [...], "system_prompt": str}.

        The Databricks AI Agent framework handles the tool-use loop — this method
        provides the tools and system prompt, and executes tool calls when invoked.
        """
        messages = model_input.get("messages", [])

        if model_input.get("tool_call"):
            tool_call = model_input["tool_call"]
            tool_name = tool_call.get("name", "")
            arguments = tool_call.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            result = self.call_tool(tool_name, arguments)
            return {"tool_result": result}

        return {
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "system_prompt": SYSTEM_PROMPT,
        }


def log_agent(config: KAConfig | None = None, registered_model_name: str = "erp_ka_agent") -> str:
    """Log the Knowledge Assistant as an MLflow pyfunc model and register it.

    Returns the model URI.
    """
    import mlflow
    from mlflow.models import infer_signature

    if config is None:
        config = KAConfig()

    agent = ERPKnowledgeAssistant(config=config)

    input_example = {
        "messages": [
            {"role": "user", "content": "What CDM fields are available for journal entries?"}
        ]
    }
    output_example = {
        "messages": input_example["messages"],
        "tools": TOOL_DEFINITIONS,
        "system_prompt": SYSTEM_PROMPT,
    }
    signature = infer_signature(input_example, output_example)

    config_path = "/tmp/ka_config.json"
    with open(config_path, "w") as f:
        json.dump(config.model_dump(), f)

    with mlflow.start_run(run_name="erp-ka-agent") as run:
        model_info = mlflow.pyfunc.log_model(
            artifact_path="erp_ka_agent",
            python_model=agent,
            artifacts={"ka_config": config_path},
            signature=signature,
            input_example=input_example,
            pip_requirements=[
                "erp-auto-mapper[databricks]",
                "mlflow>=2.14.0",
                "pydantic>=2.6.0",
            ],
        )
        model_uri = model_info.model_uri
        logger.info("Logged KA agent to %s", model_uri)

    mlflow.register_model(model_uri, registered_model_name)
    logger.info("Registered model %s", registered_model_name)

    return model_uri
