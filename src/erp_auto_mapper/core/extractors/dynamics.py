"""Microsoft Dynamics 365 / Dataverse schema extractor."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from erp_auto_mapper.core.extractors.base import (
    BaseERPExtractor,
    EntityMetadata,
    ERPConnectionConfig,
    ERPMetadata,
    ERPType,
    FieldMetadata,
    Relationship,
)

logger = logging.getLogger(__name__)

_DATAVERSE_TYPE_MAP: dict[str, str] = {
    "String": "string",
    "Memo": "string",
    "Integer": "integer",
    "BigInt": "long",
    "Decimal": "decimal",
    "Double": "double",
    "Money": "decimal",
    "Boolean": "boolean",
    "DateTime": "datetime",
    "Uniqueidentifier": "string",
    "Picklist": "integer",
    "State": "integer",
    "Status": "integer",
    "Lookup": "string",
    "Customer": "string",
    "Owner": "string",
    "Virtual": "string",
    "EntityName": "string",
    "ManagedProperty": "boolean",
}


class DynamicsExtractor(BaseERPExtractor):
    """Extract schema from Dynamics 365 / Dataverse via Web API EntityDefinitions."""

    def __init__(self, config: ERPConnectionConfig) -> None:
        super().__init__(config)
        self._api_version: str = config.extra.get("api_version", "v9.2")

    @property
    def erp_type(self) -> ERPType:
        return ERPType.DYNAMICS

    async def extract(self) -> ERPMetadata:
        entity_defs = await self._fetch_entity_definitions()
        entities: list[EntityMetadata] = []

        for edef in entity_defs:
            entity = self._parse_entity_definition(edef)
            entities.append(entity)

        return ERPMetadata(
            source=ERPType.DYNAMICS,
            source_version=self._api_version,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            entities=entities,
        )

    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        select = ",".join(fields)
        url = f"{self.config.base_url}/api/data/{self._api_version}/{entity}?$top={limit}&$select={select}"
        data = await self._request_json(url)
        result: dict[str, list[Any]] = {f: [] for f in fields}
        for row in data.get("value", []):
            for f in fields:
                if f in row:
                    result[f].append(row[f])
        return result

    async def health_check(self) -> bool:
        url = f"{self.config.base_url}/api/data/{self._api_version}/"
        try:
            async with self._build_client() as client:
                resp = await client.get(url)
                return resp.status_code < 400
        except httpx.HTTPError:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_client(self) -> httpx.AsyncClient:
        token = self.config.extra.get("access_token", "")
        headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
        }
        return httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(self.config.timeout_seconds),
            follow_redirects=True,
        )

    async def _request_json(self, url: str) -> dict[str, Any]:
        async with self._build_client() as client:
            for attempt in range(self.config.max_retries):
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.json()  # type: ignore[no-any-return]
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        wait = int(exc.response.headers.get("Retry-After", 2 ** attempt))
                        logger.info("Dynamics rate-limited, waiting %ds", wait)
                        await asyncio.sleep(wait)
                        continue
                    if exc.response.status_code == 503:
                        logger.warning("Dynamics 503, retrying in %ds", 2 ** attempt)
                        await asyncio.sleep(2 ** attempt)
                        continue
                    logger.warning("Dynamics request attempt %d failed: %s", attempt + 1, exc)
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except httpx.TimeoutException:
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"Dynamics request failed after retries: {url}")

    async def _fetch_entity_definitions(self) -> list[dict[str, Any]]:
        """Fetch EntityDefinitions with $expand=Attributes for full schema."""
        url = (
            f"{self.config.base_url}/api/data/{self._api_version}/"
            f"EntityDefinitions?$expand=Attributes&$select="
            f"LogicalName,DisplayName,Description,PrimaryIdAttribute,IsVirtual"
        )
        data = await self._request_json(url)
        return data.get("value", [])  # type: ignore[no-any-return]

    def _parse_entity_definition(self, edef: dict[str, Any]) -> EntityMetadata:
        logical_name = edef.get("LogicalName", "")
        display = edef.get("DisplayName", {})
        label = ""
        if isinstance(display, dict):
            localized = display.get("UserLocalizedLabel") or display.get("LocalizedLabels", [{}])[0] if display.get("LocalizedLabels") else {}
            if isinstance(localized, dict):
                label = localized.get("Label", "")
        primary_key = edef.get("PrimaryIdAttribute", "")
        is_virtual = edef.get("IsVirtual", False)

        fields: list[FieldMetadata] = []
        relationships: list[Relationship] = []

        for attr in edef.get("Attributes", []):
            attr_logical = attr.get("LogicalName", "")
            attr_type_str = attr.get("AttributeType", "String")
            resolved = _DATAVERSE_TYPE_MAP.get(attr_type_str, self._normalize_type(attr_type_str))

            attr_display = attr.get("DisplayName", {})
            attr_label = ""
            if isinstance(attr_display, dict):
                loc = attr_display.get("UserLocalizedLabel")
                if isinstance(loc, dict):
                    attr_label = loc.get("Label", "")

            max_len = attr.get("MaxLength")
            enum_vals: list[str] = []

            # Picklist option set values
            if attr_type_str in ("Picklist", "State", "Status"):
                option_set = attr.get("OptionSet") or attr.get("GlobalOptionSet")
                if isinstance(option_set, dict):
                    for opt in option_set.get("Options", []):
                        opt_label = opt.get("Label", {})
                        if isinstance(opt_label, dict):
                            loc = opt_label.get("UserLocalizedLabel")
                            if isinstance(loc, dict):
                                enum_vals.append(loc.get("Label", str(opt.get("Value", ""))))

            # Lookup -> relationship
            if attr_type_str == "Lookup":
                targets = attr.get("Targets", [])
                for target in targets:
                    relationships.append(Relationship(
                        source_entity=logical_name,
                        source_field=attr_logical,
                        target_entity=target,
                        target_field=f"{target}id",
                        cardinality="many-to-one",
                    ))

            fields.append(FieldMetadata(
                name=attr_logical,
                type=resolved,
                nullable=not attr.get("RequiredLevel", {}).get("Value", "None") == "ApplicationRequired",
                is_key=(attr_logical == primary_key),
                max_length=max_len,
                description=attr_label,
                enum_values=enum_vals,
            ))

        description = label
        if is_virtual:
            description = f"[Virtual] {label}"

        return EntityMetadata(
            name=logical_name,
            description=description,
            fields=fields,
            relationships=relationships,
        )
