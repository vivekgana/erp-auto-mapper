"""Sage Intacct (XML API) + Sage X3 (REST OData) schema extractor."""

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

_SAGE_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "varchar": "string",
    "char": "string",
    "integer": "integer",
    "int": "integer",
    "decimal": "decimal",
    "float": "float",
    "double": "double",
    "boolean": "boolean",
    "bool": "boolean",
    "date": "date",
    "datetime": "datetime",
    "timestamp": "datetime",
    "currency": "decimal",
    "percent": "decimal",
    "text": "string",
    "clob": "string",
    "id": "string",
}


class SageExtractor(BaseERPExtractor):
    """Extract schema from Sage Intacct (XML API) and Sage X3 (REST OData)."""

    def __init__(self, config: ERPConnectionConfig) -> None:
        super().__init__(config)
        self._variant: str = config.extra.get("variant", "intacct")  # "intacct" or "x3"
        # Intacct-specific credentials
        self._sender_id: str = config.extra.get("sender_id", "")
        self._sender_password: str = config.extra.get("sender_password", "")
        self._company_id: str = config.extra.get("company_id", "")
        self._user_id: str = config.extra.get("user_id", "")
        self._user_password: str = config.extra.get("user_password", "")
        self._objects: list[str] = config.extra.get("objects", [])

    @property
    def erp_type(self) -> ERPType:
        return ERPType.SAGE

    async def extract(self) -> ERPMetadata:
        if self._variant == "x3":
            entities = await self._extract_x3()
        else:
            entities = await self._extract_intacct()

        return ERPMetadata(
            source=ERPType.SAGE,
            source_version=f"Sage {self._variant.upper()}",
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            entities=entities,
            raw_config={"variant": self._variant, "company_id": self._company_id},
        )

    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        if self._variant == "x3":
            return await self._x3_sample_values(entity, fields, limit)
        return await self._intacct_sample_values(entity, fields, limit)

    async def health_check(self) -> bool:
        try:
            if self._variant == "x3":
                async with self._build_x3_client() as client:
                    resp = await client.get(f"{self.config.base_url}/api1/v1/")
                    return resp.status_code < 400
            else:
                async with self._build_intacct_client() as client:
                    session_id = await self._get_session(client)
                    return session_id is not None and len(session_id) > 0
        except httpx.HTTPError:
            return False

    # ==================================================================
    # Sage Intacct (XML Web Services API)
    # ==================================================================

    def _build_intacct_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={"Content-Type": "application/xml"},
            timeout=httpx.Timeout(self.config.timeout_seconds),
        )

    async def _extract_intacct(self) -> list[EntityMetadata]:
        entities: list[EntityMetadata] = []
        async with self._build_intacct_client() as client:
            session_id = await self._get_session(client)
            if not session_id:
                logger.error("Sage Intacct: failed to obtain session")
                return []

            if not self._objects:
                self._objects = await self._intacct_list_objects(client, session_id)

            for obj_name in self._objects:
                entity = await self._intacct_inspect_object(client, session_id, obj_name)
                if entity:
                    entities.append(entity)
        return entities

    async def _get_session(self, client: httpx.AsyncClient) -> str | None:
        body = self._intacct_envelope(
            "<function controlid='getSession'><getAPISession/></function>"
        )
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.post("/ia/xml/xmlgw.phtml", content=body)
                if resp.status_code == 429:
                    await asyncio.sleep(int(resp.headers.get("Retry-After", "2")))
                    continue
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
                session_el = root.find(".//sessionid")
                if session_el is not None and session_el.text:
                    return session_el.text
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                logger.warning("Sage session error (attempt %d): %s", attempt + 1, exc)
        return None

    async def _intacct_post(
        self, client: httpx.AsyncClient, session_id: str, function_xml: str
    ) -> str | None:
        body = self._intacct_envelope(function_xml, session_id=session_id)
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.post("/ia/xml/xmlgw.phtml", content=body)
                if resp.status_code == 429:
                    await asyncio.sleep(int(resp.headers.get("Retry-After", "2")))
                    continue
                resp.raise_for_status()
                return resp.text
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                logger.warning("Sage request error (attempt %d): %s", attempt + 1, exc)
        return None

    def _intacct_envelope(self, function_body: str, session_id: str = "") -> str:
        auth_block = (
            f"<sessionid>{session_id}</sessionid>"
            if session_id
            else (
                f"<login><userid>{self._user_id}</userid>"
                f"<companyid>{self._company_id}</companyid>"
                f"<password>{self._user_password}</password></login>"
            )
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<request><control>"
            f"<senderid>{self._sender_id}</senderid>"
            f"<password>{self._sender_password}</password>"
            "<controlid>erp-auto-mapper</controlid>"
            "<uniqueid>false</uniqueid>"
            "<dtdversion>3.0</dtdversion>"
            "<includewhitespace>false</includewhitespace>"
            "</control><operation>"
            f"<authentication>{auth_block}</authentication>"
            f"<content>{function_body}</content>"
            "</operation></request>"
        )

    async def _intacct_list_objects(
        self, client: httpx.AsyncClient, session_id: str
    ) -> list[str]:
        func = "<function controlid='list'><inspect detail='0'><object>*</object></inspect></function>"
        resp_text = await self._intacct_post(client, session_id, func)
        if not resp_text:
            return []
        root = ET.fromstring(resp_text)
        return [t.text.strip() for t in root.iter("type") if t.text]

    async def _intacct_inspect_object(
        self, client: httpx.AsyncClient, session_id: str, obj_name: str
    ) -> EntityMetadata | None:
        func = (
            f"<function controlid='inspect_{obj_name}'>"
            f"<inspect><object>{obj_name}</object><detail>1</detail></inspect>"
            f"</function>"
        )
        resp_text = await self._intacct_post(client, session_id, func)
        if not resp_text:
            return None
        try:
            root = ET.fromstring(resp_text)
        except ET.ParseError:
            logger.warning("Sage: parse error inspecting %s", obj_name)
            return None

        fields: list[FieldMetadata] = []
        relationships: list[Relationship] = []

        for field_el in root.iter("Field"):
            fname = self._el_text(field_el, "Name") or self._el_text(field_el, "DataName") or ""
            raw_type = (self._el_text(field_el, "DataType") or self._el_text(field_el, "Type") or "string").lower()
            ftype = _SAGE_TYPE_MAP.get(raw_type, self._normalize_type(raw_type))
            nullable = (self._el_text(field_el, "Required") or "").lower() != "true"
            is_key = (self._el_text(field_el, "IsKey") or self._el_text(field_el, "ID") or "").lower() == "true"
            desc = self._el_text(field_el, "Description") or ""
            max_len_str = self._el_text(field_el, "MaxLength")
            max_len = int(max_len_str) if max_len_str and max_len_str.isdigit() else None

            related = self._el_text(field_el, "RelatedObject")
            if related:
                relationships.append(Relationship(
                    source_entity=obj_name,
                    source_field=fname,
                    target_entity=related,
                    target_field="",
                    cardinality="many-to-one",
                ))

            if fname:
                fields.append(FieldMetadata(
                    name=fname,
                    type=ftype,
                    nullable=nullable,
                    is_key=is_key,
                    max_length=max_len,
                    description=desc,
                ))

        if not fields:
            return None

        return EntityMetadata(
            name=obj_name,
            description=f"Sage Intacct {obj_name}",
            fields=fields,
            relationships=relationships,
        )

    async def _intacct_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        result: dict[str, list[Any]] = {f: [] for f in fields}
        fields_xml = "".join(f"<field>{f}</field>" for f in fields)
        func = (
            f"<function controlid='sample_{entity}'>"
            f"<readByQuery><object>{entity}</object>"
            f"<fields>{fields_xml}</fields>"
            f"<query></query><pagesize>{limit}</pagesize>"
            f"</readByQuery></function>"
        )
        async with self._build_intacct_client() as client:
            session_id = await self._get_session(client)
            if not session_id:
                return result
            resp_text = await self._intacct_post(client, session_id, func)
            if not resp_text:
                return result
            try:
                root = ET.fromstring(resp_text)
                for record in root.iter(entity.lower()):
                    for f in fields:
                        el = record.find(f)
                        if el is not None and el.text:
                            result[f].append(el.text)
            except ET.ParseError:
                logger.warning("Sage: parse error reading samples for %s", entity)
        return result

    # ==================================================================
    # Sage X3 (REST / OData)
    # ==================================================================

    def _build_x3_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {"Accept": "application/json"}
        auth = None
        token = self.config.extra.get("access_token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.config.auth_method == "basic":
            auth = httpx.BasicAuth(
                self.config.extra.get("username", ""),
                self.config.extra.get("password", ""),
            )
        return httpx.AsyncClient(
            headers=headers,
            auth=auth,
            timeout=httpx.Timeout(self.config.timeout_seconds),
            follow_redirects=True,
        )

    async def _extract_x3(self) -> list[EntityMetadata]:
        endpoints: list[str] = self.config.extra.get("endpoints", [])
        entities: list[EntityMetadata] = []

        async with self._build_x3_client() as client:
            if not endpoints:
                endpoints = await self._x3_discover_endpoints(client)
            for ep in endpoints:
                try:
                    entity = await self._x3_describe(client, ep)
                    if entity:
                        entities.append(entity)
                except Exception:
                    logger.warning("X3 describe failed for: %s", ep, exc_info=True)
        return entities

    async def _x3_discover_endpoints(self, client: httpx.AsyncClient) -> list[str]:
        url = f"{self.config.base_url}/api1/v1/$service"
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url)
                if resp.status_code == 429:
                    await asyncio.sleep(int(resp.headers.get("Retry-After", "5")))
                    continue
                resp.raise_for_status()
                return [
                    item.get("name", "")
                    for item in resp.json().get("value", [])
                    if isinstance(item, dict) and item.get("name")
                ]
            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return []

    async def _x3_describe(
        self, client: httpx.AsyncClient, endpoint: str
    ) -> EntityMetadata | None:
        url = f"{self.config.base_url}/api1/v1/{endpoint}/$schema"
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    return None
                if resp.status_code == 429:
                    await asyncio.sleep(int(resp.headers.get("Retry-After", "5")))
                    continue
                resp.raise_for_status()
                schema = resp.json()
                return self._x3_parse_schema(endpoint, schema)
            except httpx.TimeoutException:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        return None

    def _x3_parse_schema(self, endpoint: str, schema: dict[str, Any]) -> EntityMetadata:
        fields: list[FieldMetadata] = []
        relationships: list[Relationship] = []

        for prop_name, prop_def in schema.get("properties", {}).items():
            ref = prop_def.get("$ref", "")
            if ref:
                relationships.append(Relationship(
                    source_entity=endpoint,
                    source_field=prop_name,
                    target_entity=ref.split("/")[-1],
                    target_field="",
                    cardinality="many-to-one",
                ))
                continue

            raw_type = prop_def.get("type", "string")
            if isinstance(raw_type, list):
                raw_type = next((t for t in raw_type if t != "null"), "string")
            resolved = _SAGE_TYPE_MAP.get(raw_type.lower(), self._normalize_type(raw_type))

            fields.append(FieldMetadata(
                name=prop_name,
                type=resolved,
                nullable=not prop_def.get("required", False),
                is_key=prop_def.get("key", False),
                max_length=prop_def.get("maxLength"),
                description=prop_def.get("description", ""),
            ))

        return EntityMetadata(
            name=endpoint,
            description=schema.get("description", ""),
            fields=fields,
            relationships=relationships,
        )

    async def _x3_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        result: dict[str, list[Any]] = {f: [] for f in fields}
        url = f"{self.config.base_url}/api1/v1/{entity}?$top={limit}&$select={','.join(fields)}"
        async with self._build_x3_client() as client:
            for attempt in range(self.config.max_retries):
                try:
                    resp = await client.get(url)
                    if resp.status_code == 429:
                        await asyncio.sleep(int(resp.headers.get("Retry-After", "5")))
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
                    logger.warning("X3 sample query failed: %s", exc)
                    break
        return result

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _el_text(parent: ET.Element, tag: str) -> str | None:
        el = parent.find(tag)
        if el is not None and el.text:
            return el.text.strip()
        return None
