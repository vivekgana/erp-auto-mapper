"""Oracle ERP Cloud (Fusion) schema extractor via REST describe endpoints."""

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

# Oracle Fusion REST type mapping
_ORACLE_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "decimal",
    "boolean": "boolean",
    "date": "date",
    "datetime": "datetime",
    "object": "string",
    "array": "string",
}


class OracleERPExtractor(BaseERPExtractor):
    """Extract schema from Oracle ERP Cloud via REST /describe and FBDI templates."""

    def __init__(self, config: ERPConnectionConfig) -> None:
        super().__init__(config)
        self._api_version: str = config.extra.get("api_version", "11.13.18.05")

    @property
    def erp_type(self) -> ERPType:
        return ERPType.ORACLE

    async def extract(self) -> ERPMetadata:
        resources = await self._discover_resources()
        entities: list[EntityMetadata] = []
        relationships: list[Relationship] = []

        for resource_name, resource_href in resources:
            try:
                entity, rels = await self._describe_resource(resource_name, resource_href)
                entities.append(entity)
                relationships.extend(rels)
            except Exception:
                logger.warning("Failed to describe Oracle resource: %s", resource_name, exc_info=True)

        return ERPMetadata(
            source=ERPType.ORACLE,
            source_version=self._api_version,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            entities=entities,
            raw_config={"api_version": self._api_version},
        )

    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        url = f"{self.config.base_url}/fscmRestApi/resources/{self._api_version}/{entity}?limit={limit}&fields={','.join(fields)}"
        data = await self._request_json(url)
        result: dict[str, list[Any]] = {f: [] for f in fields}
        for item in data.get("items", []):
            for f in fields:
                if f in item:
                    result[f].append(item[f])
        return result

    async def health_check(self) -> bool:
        url = f"{self.config.base_url}/fscmRestApi/resources/{self._api_version}"
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
        headers: dict[str, str] = {"Accept": "application/json"}
        auth = None
        if self.config.auth_method == "basic":
            creds = self.config.extra
            auth = httpx.BasicAuth(creds["username"], creds["password"])
        elif self.config.auth_method == "oauth2":
            token = self.config.extra.get("access_token", "")
            headers["Authorization"] = f"Bearer {token}"
        return httpx.AsyncClient(
            headers=headers,
            auth=auth,
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
                        logger.info("Oracle rate-limited, waiting %ds", wait)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("Oracle request attempt %d failed: %s", attempt + 1, exc)
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except httpx.TimeoutException:
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"Oracle request failed after retries: {url}")

    async def _discover_resources(self) -> list[tuple[str, str]]:
        url = f"{self.config.base_url}/fscmRestApi/resources/{self._api_version}"
        data = await self._request_json(url)
        resources: list[tuple[str, str]] = []
        for item in data.get("items", []):
            name = item.get("name", "")
            href = item.get("links", [{}])[0].get("href", "") if item.get("links") else ""
            if name:
                resources.append((name, href))
        return resources

    async def _describe_resource(
        self, name: str, href: str
    ) -> tuple[EntityMetadata, list[Relationship]]:
        describe_url = f"{href}/describe" if href else (
            f"{self.config.base_url}/fscmRestApi/resources/{self._api_version}/{name}/describe"
        )
        desc_data = await self._request_json(describe_url)
        fields: list[FieldMetadata] = []
        relationships: list[Relationship] = []

        # Standard attributes
        for attr in desc_data.get("attributes", []):
            attr_name = attr.get("name", "")
            attr_type = attr.get("type", "string")
            resolved = _ORACLE_TYPE_MAP.get(attr_type.lower(), self._normalize_type(attr_type))
            fields.append(FieldMetadata(
                name=attr_name,
                type=resolved,
                nullable=not attr.get("required", False),
                is_key=attr.get("primaryKey", False),
                max_length=attr.get("maxLength"),
                description=attr.get("title", ""),
            ))

        # Descriptive Flex Fields (DFF)
        for dff in desc_data.get("descriptiveFlexFields", []):
            fields.append(FieldMetadata(
                name=dff.get("name", ""),
                type="string",
                nullable=True,
                description=f"DFF: {dff.get('prompt', '')}",
            ))

        # Extensible Flex Fields (EFF)
        for eff in desc_data.get("extensibleFlexFields", []):
            fields.append(FieldMetadata(
                name=eff.get("name", ""),
                type="string",
                nullable=True,
                description=f"EFF: {eff.get('prompt', '')}",
            ))

        # LOV (List of Values)
        for attr in desc_data.get("attributes", []):
            lov = attr.get("listOfValues")
            if lov and isinstance(lov, dict):
                lov_values = lov.get("values", [])
                for fm in fields:
                    if fm.name == attr.get("name"):
                        fm.enum_values = [str(v) for v in lov_values[:50]]

        # Child resources as relationships
        for child in desc_data.get("children", []):
            child_name = child.get("name", "")
            if child_name:
                relationships.append(Relationship(
                    source_entity=name,
                    source_field=child_name,
                    target_entity=child_name,
                    target_field="",
                    cardinality="one-to-many",
                ))

        entity = EntityMetadata(
            name=name,
            description=desc_data.get("title", ""),
            fields=fields,
            relationships=relationships,
        )
        return entity, relationships
