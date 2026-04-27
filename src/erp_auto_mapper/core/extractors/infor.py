"""Infor CloudSuite schema extractor via ION API Gateway + BOD schemas."""

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

_INFOR_TYPE_MAP: dict[str, str] = {
    "StringType": "string",
    "string": "string",
    "IndicatorType": "boolean",
    "AmountType": "decimal",
    "QuantityType": "decimal",
    "NumberType": "decimal",
    "integer": "integer",
    "decimal": "decimal",
    "boolean": "boolean",
    "DateType": "date",
    "DateTimeType": "datetime",
    "date": "date",
    "dateTime": "datetime",
    "IdentifierType": "string",
    "CodeType": "string",
    "NameType": "string",
    "TextType": "string",
    "NormalizedStringType": "string",
    "URIType": "string",
}

_XSD_NS = "http://www.w3.org/2001/XMLSchema"


class InforExtractor(BaseERPExtractor):
    """Extract schema from Infor CloudSuite via ION API and OAGIS BOD schemas."""

    def __init__(self, config: ERPConnectionConfig) -> None:
        super().__init__(config)
        self._ion_path: str = config.extra.get("ion_api_path", "/IONSERVICES/api/ion/v1")

    @property
    def erp_type(self) -> ERPType:
        return ERPType.INFOR

    async def extract(self) -> ERPMetadata:
        bods: list[str] = self.config.extra.get("bods", [])
        entities: list[EntityMetadata] = []

        async with self._build_client() as client:
            if not bods:
                bods = await self._discover_bods(client)
            for bod in bods:
                try:
                    bod_entities = await self._fetch_bod_schema(client, bod)
                    entities.extend(bod_entities)
                except Exception:
                    logger.warning("Failed to parse Infor BOD: %s", bod, exc_info=True)

        return ERPMetadata(
            source=ERPType.INFOR,
            source_version="Infor CloudSuite ION",
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            entities=entities,
            raw_config={"bods": bods},
        )

    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        url = f"{self._ion_path}/datalakeapi/v1/datacatalog/{entity}/data?limit={limit}"
        result: dict[str, list[Any]] = {f: [] for f in fields}
        async with self._build_client() as client:
            for attempt in range(self.config.max_retries):
                try:
                    resp = await client.get(url)
                    if resp.status_code == 429:
                        await asyncio.sleep(int(resp.headers.get("Retry-After", "5")))
                        continue
                    resp.raise_for_status()
                    rows = resp.json().get("rows", resp.json().get("data", []))
                    for row in rows:
                        for f in fields:
                            if f in row:
                                result[f].append(row[f])
                    return result
                except httpx.TimeoutException:
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except httpx.HTTPStatusError as exc:
                    logger.warning("Infor data query failed: %s", exc)
                    break
        return result

    async def health_check(self) -> bool:
        async with self._build_client() as client:
            try:
                resp = await client.get(f"{self._ion_path}/healthcheck")
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
        }
        return httpx.AsyncClient(
            base_url=self.config.base_url,
            headers=headers,
            timeout=httpx.Timeout(self.config.timeout_seconds),
            follow_redirects=True,
        )

    async def _discover_bods(self, client: httpx.AsyncClient) -> list[str]:
        url = f"{self._ion_path}/messaging/v2/bod"
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url)
                if resp.status_code == 429:
                    await asyncio.sleep(int(resp.headers.get("Retry-After", "5")))
                    continue
                resp.raise_for_status()
                items = resp.json().get("bods", resp.json().get("items", []))
                return [i if isinstance(i, str) else i.get("name", "") for i in items]
            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return []

    async def _fetch_bod_schema(
        self, client: httpx.AsyncClient, bod: str
    ) -> list[EntityMetadata]:
        url = f"{self._ion_path}/messaging/v2/bod/{bod}/schema"
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url, headers={"Accept": "application/xml"})
                if resp.status_code == 404:
                    return []
                if resp.status_code == 429:
                    await asyncio.sleep(int(resp.headers.get("Retry-After", "5")))
                    continue
                resp.raise_for_status()
                return self._parse_bod_xml(bod, resp.text)
            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return []

    def _parse_bod_xml(self, bod: str, xml_text: str) -> list[EntityMetadata]:
        """Parse OAGIS BOD XSD, mapping complexType elements to entity fields."""
        entities: list[EntityMetadata] = []
        root = ET.fromstring(xml_text)

        for ct in root.iter(f"{{{_XSD_NS}}}complexType"):
            ct_name = ct.attrib.get("name", "")
            if not ct_name:
                continue

            fields: list[FieldMetadata] = []
            relationships: list[Relationship] = []

            for container_tag in ("sequence", "all", "choice"):
                for container in ct.iter(f"{{{_XSD_NS}}}{container_tag}"):
                    for el in container.findall(f"{{{_XSD_NS}}}element"):
                        el_name = el.attrib.get("name", "")
                        el_type = el.attrib.get("type", "string")
                        local_type = el_type.split(":")[-1] if ":" in el_type else el_type
                        min_occurs = el.attrib.get("minOccurs", "0")
                        max_occurs = el.attrib.get("maxOccurs", "1")

                        # Complex sub-elements become relationships
                        if max_occurs == "unbounded" or (
                            local_type.endswith("Type") and local_type not in _INFOR_TYPE_MAP
                        ):
                            relationships.append(Relationship(
                                source_entity=f"{bod}.{ct_name}",
                                source_field=el_name,
                                target_entity=f"{bod}.{local_type}",
                                target_field="",
                                cardinality="one-to-many" if max_occurs == "unbounded" else "many-to-one",
                            ))
                            continue

                        resolved = _INFOR_TYPE_MAP.get(local_type, self._normalize_type(local_type))
                        desc = ""
                        ann = el.find(f"{{{_XSD_NS}}}annotation")
                        if ann is not None:
                            doc = ann.find(f"{{{_XSD_NS}}}documentation")
                            if doc is not None and doc.text:
                                desc = doc.text.strip()

                        fields.append(FieldMetadata(
                            name=el_name,
                            type=resolved,
                            nullable=(min_occurs == "0"),
                            description=desc,
                        ))

            if fields or relationships:
                entities.append(EntityMetadata(
                    name=f"{bod}.{ct_name}",
                    fields=fields,
                    relationships=relationships,
                ))

        return entities
