"""Epicor Kinetic schema extractor via REST v2 + OData $metadata."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

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

_EPICOR_TYPE_MAP: dict[str, str] = {
    "Edm.String": "string",
    "Edm.Int32": "integer",
    "Edm.Int64": "long",
    "Edm.Decimal": "decimal",
    "Edm.Double": "double",
    "Edm.Single": "float",
    "Edm.Boolean": "boolean",
    "Edm.Date": "date",
    "Edm.DateTimeOffset": "datetime",
    "Edm.TimeOfDay": "time",
    "Edm.Binary": "binary",
    "Edm.Guid": "string",
    "Edm.Byte": "integer",
    "Edm.Int16": "integer",
}

_EDMX_NS = "http://docs.oasis-open.org/odata/ns/edm"


class EpicorExtractor(BaseERPExtractor):
    """Extract schema from Epicor Kinetic REST v2 OData service metadata."""

    def __init__(self, config: ERPConnectionConfig) -> None:
        super().__init__(config)
        self._company: str = config.extra.get("company", "")
        self._api_version: str = config.extra.get("api_version", "v2")

    @property
    def erp_type(self) -> ERPType:
        return ERPType.EPICOR

    async def extract(self) -> ERPMetadata:
        services: list[str] = self.config.extra.get("services", [])
        entities: list[EntityMetadata] = []

        async with self._build_client() as client:
            if not services:
                services = await self._discover_services(client)
            for svc in services:
                try:
                    svc_entities = await self._fetch_metadata(client, svc)
                    entities.extend(svc_entities)
                except Exception:
                    logger.warning("Failed to extract Epicor service: %s", svc, exc_info=True)

        return ERPMetadata(
            source=ERPType.EPICOR,
            source_version=f"Epicor Kinetic {self._api_version}",
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            entities=entities,
            raw_config={"company": self._company, "services": services},
        )

    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        select = ",".join(fields)
        parts = entity.rsplit(".", 1)
        svc = parts[0] if len(parts) > 1 else ""
        ename = parts[-1]
        url = f"/api/{self._api_version}/odata/{self._company}/{svc}/{ename}?$top={limit}&$select={select}"
        result: dict[str, list[Any]] = {f: [] for f in fields}
        async with self._build_client() as client:
            for attempt in range(self.config.max_retries):
                try:
                    resp = await client.get(url)
                    if resp.status_code == 429:
                        await asyncio.sleep(int(resp.headers.get("Retry-After", "2")))
                        continue
                    resp.raise_for_status()
                    for row in resp.json().get("value", []):
                        for f in fields:
                            if f in row:
                                result[f].append(row[f])
                    return result
                except httpx.TimeoutException:
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except httpx.HTTPStatusError as exc:
                    logger.warning("Epicor sample query failed: %s", exc)
                    break
        return result

    async def health_check(self) -> bool:
        async with self._build_client() as client:
            try:
                resp = await client.get(f"/api/{self._api_version}/")
                return resp.status_code < 400
            except httpx.HTTPError:
                return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {"Accept": "application/json"}
        auth = None
        api_key = self.config.extra.get("api_key", "")
        token = self.config.extra.get("access_token", "")
        if api_key:
            headers["Authorization"] = f"Basic {api_key}"
        elif token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.config.auth_method == "basic":
            creds = self.config.extra
            auth = httpx.BasicAuth(creds.get("username", ""), creds.get("password", ""))
        return httpx.AsyncClient(
            base_url=self.config.base_url,
            headers=headers,
            auth=auth,
            timeout=httpx.Timeout(self.config.timeout_seconds),
            follow_redirects=True,
        )

    async def _discover_services(self, client: httpx.AsyncClient) -> list[str]:
        url = f"/api/{self._api_version}/odata/{self._company}"
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url)
                if resp.status_code == 429:
                    await asyncio.sleep(int(resp.headers.get("Retry-After", "2")))
                    continue
                resp.raise_for_status()
                data = resp.json()
                return [str(s.get("name", s.get("url", ""))) for s in data.get("value", []) if isinstance(s, dict)]
            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return []

    async def _fetch_metadata(
        self, client: httpx.AsyncClient, service: str
    ) -> list[EntityMetadata]:
        url = f"/api/{self._api_version}/odata/{self._company}/{service}/$metadata"
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url, headers={"Accept": "application/xml"})
                if resp.status_code == 404:
                    return []
                if resp.status_code == 429:
                    await asyncio.sleep(int(resp.headers.get("Retry-After", "2")))
                    continue
                resp.raise_for_status()
                return self._parse_odata_xml(service, resp.text)
            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return []

    def _parse_odata_xml(self, service: str, xml_text: str) -> list[EntityMetadata]:
        entities: list[EntityMetadata] = []
        root = ET.fromstring(xml_text)

        for schema in root.iter(f"{{{_EDMX_NS}}}Schema"):
            for et in schema.iter(f"{{{_EDMX_NS}}}EntityType"):
                et_name = et.attrib.get("Name", "")
                key_names: set[str] = set()
                key_el = et.find(f"{{{_EDMX_NS}}}Key")
                if key_el is not None:
                    for pr in key_el.iter(f"{{{_EDMX_NS}}}PropertyRef"):
                        key_names.add(pr.attrib.get("Name", ""))

                fields: list[FieldMetadata] = []
                relationships: list[Relationship] = []

                for prop in et.iter(f"{{{_EDMX_NS}}}Property"):
                    pname = prop.attrib.get("Name", "")
                    ptype = prop.attrib.get("Type", "Edm.String")
                    nullable = prop.attrib.get("Nullable", "true").lower() == "true"
                    max_len_str = prop.attrib.get("MaxLength")
                    max_len = int(max_len_str) if max_len_str and max_len_str.isdigit() else None
                    resolved = _EPICOR_TYPE_MAP.get(ptype, self._normalize_type(ptype.split(".")[-1]))

                    fields.append(FieldMetadata(
                        name=pname,
                        type=resolved,
                        nullable=nullable,
                        is_key=(pname in key_names),
                        max_length=max_len,
                    ))

                for nav in et.iter(f"{{{_EDMX_NS}}}NavigationProperty"):
                    nav_name = nav.attrib.get("Name", "")
                    nav_type = nav.attrib.get("Type", "")
                    is_collection = "Collection" in nav_type
                    target = nav_type.replace("Collection(", "").rstrip(")").split(".")[-1]
                    if target:
                        relationships.append(Relationship(
                            source_entity=f"{service}.{et_name}",
                            source_field=nav_name,
                            target_entity=f"{service}.{target}",
                            target_field="",
                            cardinality="one-to-many" if is_collection else "many-to-one",
                        ))

                entities.append(EntityMetadata(
                    name=f"{service}.{et_name}",
                    fields=fields,
                    relationships=relationships,
                ))

        return entities
