"""Workday schema extractor via REST OpenAPI specs + WSDL + RaaS reports."""

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

_WD_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "decimal",
    "boolean": "boolean",
    "date": "date",
    "dateTime": "datetime",
    "decimal": "decimal",
    "base64Binary": "binary",
    "anyURI": "string",
}

_XSD_NS = "http://www.w3.org/2001/XMLSchema"


class WorkdayExtractor(BaseERPExtractor):
    """Extract schema from Workday REST (OpenAPI), SOAP (WSDL), and RaaS endpoints."""

    def __init__(self, config: ERPConnectionConfig) -> None:
        super().__init__(config)
        self._tenant: str = config.extra.get("tenant", "")
        self._api_version: str = config.extra.get("api_version", "v42.0")

    @property
    def erp_type(self) -> ERPType:
        return ERPType.WORKDAY

    async def extract(self) -> ERPMetadata:
        entities: list[EntityMetadata] = []
        services: list[str] = self.config.extra.get("services", [])
        wsdl_services: list[str] = self.config.extra.get("wsdl_services", [])
        raas_reports: list[str] = self.config.extra.get("raas_reports", [])

        async with self._build_client() as client:
            for svc in services:
                svc_entities = await self._extract_openapi(client, svc)
                entities.extend(svc_entities)

            for ws in wsdl_services:
                wsdl_entities = await self._extract_wsdl(client, ws)
                entities.extend(wsdl_entities)

            for report_path in raas_reports:
                report_entity = await self._extract_raas(client, report_path)
                if report_entity:
                    entities.append(report_entity)

        return ERPMetadata(
            source=ERPType.WORKDAY,
            source_version=self._api_version,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            entities=entities,
            raw_config={"tenant": self._tenant, "api_version": self._api_version},
        )

    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        url = f"{self.config.base_url}/ccx/api/{self._api_version}/{self._tenant}/{entity}?limit={limit}"
        data = await self._request_json(url)
        result: dict[str, list[Any]] = {f: [] for f in fields}
        for row in data.get("data", []):
            for f in fields:
                if f in row:
                    result[f].append(row[f])
        return result

    async def health_check(self) -> bool:
        url = f"{self.config.base_url}/ccx/api/{self._api_version}/{self._tenant}/"
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
        }
        return httpx.AsyncClient(
            base_url=self.config.base_url,
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
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("Workday request attempt %d: %s", attempt + 1, exc)
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except httpx.TimeoutException:
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"Workday request failed after retries: {url}")

    # ---- OpenAPI ----

    async def _extract_openapi(
        self, client: httpx.AsyncClient, service: str
    ) -> list[EntityMetadata]:
        url = f"/ccx/api/{self._api_version}/{self._tenant}/{service}/openapi.json"
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                return self._parse_openapi(service, resp.json())
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    await asyncio.sleep(int(exc.response.headers.get("Retry-After", "5")))
                    continue
                break
            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return []

    def _parse_openapi(self, service: str, spec: dict[str, Any]) -> list[EntityMetadata]:
        entities: list[EntityMetadata] = []
        for name, schema in spec.get("components", {}).get("schemas", {}).items():
            if schema.get("type") != "object":
                continue
            required_fields = set(schema.get("required", []))
            fields: list[FieldMetadata] = []
            relationships: list[Relationship] = []

            for pname, pdef in schema.get("properties", {}).items():
                ref = pdef.get("$ref", "")
                if ref:
                    target = ref.rsplit("/", 1)[-1]
                    relationships.append(Relationship(
                        source_entity=f"{service}.{name}",
                        source_field=pname,
                        target_entity=f"{service}.{target}",
                        target_field="id",
                        cardinality="many-to-one",
                    ))
                    continue
                raw_type = pdef.get("type", "string")
                if pdef.get("format") == "date":
                    raw_type = "date"
                elif pdef.get("format") == "date-time":
                    raw_type = "dateTime"
                resolved = _WD_TYPE_MAP.get(raw_type, self._normalize_type(raw_type))
                fields.append(FieldMetadata(
                    name=pname,
                    type=resolved,
                    nullable=pname not in required_fields,
                    is_key=(pname == "id"),
                    description=pdef.get("description", ""),
                    enum_values=pdef.get("enum", []),
                    max_length=pdef.get("maxLength"),
                ))
            entities.append(EntityMetadata(
                name=f"{service}.{name}",
                description=schema.get("description", ""),
                fields=fields,
                relationships=relationships,
            ))
        return entities

    # ---- WSDL (SOAP) ----

    async def _extract_wsdl(
        self, client: httpx.AsyncClient, wsdl_service: str
    ) -> list[EntityMetadata]:
        url = f"/ccx/service/{self._tenant}/{wsdl_service}?wsdl"
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url, headers={"Accept": "application/xml"})
                if resp.status_code == 404:
                    return []
                resp.raise_for_status()
                return self._parse_wsdl(wsdl_service, resp.text)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    await asyncio.sleep(int(exc.response.headers.get("Retry-After", "5")))
                    continue
                break
            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return []

    def _parse_wsdl(self, service: str, xml_text: str) -> list[EntityMetadata]:
        entities: list[EntityMetadata] = []
        root = ET.fromstring(xml_text)
        for ct in root.iter(f"{{{_XSD_NS}}}complexType"):
            ct_name = ct.attrib.get("name", "")
            if not ct_name:
                continue
            fields: list[FieldMetadata] = []
            for el in ct.iter(f"{{{_XSD_NS}}}element"):
                el_name = el.attrib.get("name", "")
                el_type = el.attrib.get("type", "xsd:string")
                local_type = el_type.split(":")[-1]
                resolved = _WD_TYPE_MAP.get(local_type, self._normalize_type(local_type))
                fields.append(FieldMetadata(
                    name=el_name,
                    type=resolved,
                    nullable=el.attrib.get("minOccurs", "0") == "0",
                ))
            if fields:
                entities.append(EntityMetadata(
                    name=f"{service}.{ct_name}",
                    fields=fields,
                ))
        return entities

    # ---- RaaS (Report as a Service) ----

    async def _extract_raas(
        self, client: httpx.AsyncClient, report_path: str
    ) -> EntityMetadata | None:
        """Fetch a RaaS report with zero rows to discover column schema."""
        sep = "&" if "?" in report_path else "?"
        url = f"{report_path}{sep}format=json&count=0"
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json()
                entries = data.get("Report_Entry", [])
                if not entries:
                    return None
                columns = list(entries[0].keys())
                fields = [FieldMetadata(name=c, type="string", nullable=True) for c in columns]
                report_name = report_path.rsplit("/", 1)[-1].split("?")[0]
                return EntityMetadata(
                    name=f"raas.{report_name}",
                    description=f"RaaS report: {report_name}",
                    fields=fields,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    await asyncio.sleep(int(exc.response.headers.get("Retry-After", "5")))
                    continue
                break
            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return None
