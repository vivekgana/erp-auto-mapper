"""SAP S/4HANA schema extractor via OData v4 $metadata."""

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

# SAP-specific ABAP/CDS type mapping beyond the base normaliser.
_SAP_TYPE_MAP: dict[str, str] = {
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
    # SAP ABAP types surfaced via annotations
    "DATS": "date",
    "TIMS": "time",
    "NUMC": "string",
    "CHAR": "string",
    "DEC": "decimal",
    "CURR": "decimal",
    "QUAN": "decimal",
    "UNIT": "string",
    "CLNT": "string",
    "LANG": "string",
    "CUKY": "string",
}

_OData_NS = "http://docs.oasis-open.org/odata/ns/edm"
_SAP_COMMON_NS = "com.sap.vocabularies.Common.v1"


class SAPExtractor(BaseERPExtractor):
    """Extract schema metadata from SAP S/4HANA Cloud or on-prem via OData v4."""

    def __init__(self, config: ERPConnectionConfig) -> None:
        super().__init__(config)
        self._sap_client: str = config.extra.get("sap_client", "100")

    @property
    def erp_type(self) -> ERPType:
        return ERPType.SAP

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def extract(self) -> ERPMetadata:
        """Fetch $metadata XML and parse entity types, fields, and nav props."""
        xml_text = await self._fetch_metadata()
        root = ET.fromstring(xml_text)
        entities, relationships = self._parse_metadata(root)

        return ERPMetadata(
            source=ERPType.SAP,
            source_version=self._detect_version(root),
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            entities=entities,
            raw_config={"sap_client": self._sap_client},
        )

    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        """Query OData entity set with $top and $select for sample rows."""
        select = ",".join(fields)
        url = f"{self.config.base_url}/{entity}?$top={limit}&$select={select}&sap-client={self._sap_client}"
        data = await self._request_json(url)
        result: dict[str, list[Any]] = {f: [] for f in fields}
        for row in data.get("value", []):
            for f in fields:
                if f in row:
                    result[f].append(row[f])
        return result

    async def health_check(self) -> bool:
        url = f"{self.config.base_url}/?sap-client={self._sap_client}"
        try:
            async with self._build_client() as client:
                resp = await client.get(url)
                return resp.status_code < 400
        except httpx.HTTPError:
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "sap-client": self._sap_client,
        }
        auth = None
        if self.config.auth_method == "basic":
            creds = self.config.extra
            auth = httpx.BasicAuth(creds["username"], creds["password"])
        return httpx.AsyncClient(
            headers=headers,
            auth=auth,
            timeout=httpx.Timeout(self.config.timeout_seconds),
            follow_redirects=True,
        )

    async def _fetch_metadata(self) -> str:
        url = f"{self.config.base_url}/$metadata?sap-client={self._sap_client}"
        async with self._build_client() as client:
            for attempt in range(self.config.max_retries):
                try:
                    resp = await client.get(url, headers={"Accept": "application/xml"})
                    resp.raise_for_status()
                    return resp.text
                except (httpx.HTTPStatusError, httpx.TimeoutException) as exc:
                    logger.warning("SAP $metadata attempt %d failed: %s", attempt + 1, exc)
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
        raise RuntimeError("Failed to fetch SAP $metadata after retries")

    async def _request_json(self, url: str) -> dict[str, Any]:
        async with self._build_client() as client:
            for attempt in range(self.config.max_retries):
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.json()  # type: ignore[no-any-return]
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        retry_after = int(exc.response.headers.get("Retry-After", 2 ** attempt))
                        logger.info("SAP rate-limited, sleeping %ds", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    logger.warning("SAP request attempt %d failed: %s", attempt + 1, exc)
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except httpx.TimeoutException:
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"SAP request failed after retries: {url}")

    # ------------------------------------------------------------------
    # XML parsing
    # ------------------------------------------------------------------

    def _parse_metadata(self, root: ET.Element) -> tuple[list[EntityMetadata], list[Relationship]]:
        entities: list[EntityMetadata] = []
        relationships: list[Relationship] = []

        for schema in root.iter(f"{{{_OData_NS}}}Schema"):
            for et in schema.iter(f"{{{_OData_NS}}}EntityType"):
                entity_name = et.attrib.get("Name", "")
                description = self._annotation_text(et, "Label") or ""
                key_names = {
                    pr.attrib["Name"]
                    for key in et.iter(f"{{{_OData_NS}}}Key")
                    for pr in key.iter(f"{{{_OData_NS}}}PropertyRef")
                }

                fields: list[FieldMetadata] = []
                for prop in et.iter(f"{{{_OData_NS}}}Property"):
                    name = prop.attrib.get("Name", "")
                    raw_type = prop.attrib.get("Type", "Edm.String")
                    sap_type = self._annotation_text(prop, "semantics.type") or ""
                    resolved = _SAP_TYPE_MAP.get(sap_type, _SAP_TYPE_MAP.get(raw_type, self._normalize_type(raw_type.split(".")[-1])))
                    nullable = prop.attrib.get("Nullable", "true").lower() == "true"
                    max_len = int(prop.attrib["MaxLength"]) if "MaxLength" in prop.attrib else None
                    desc = self._annotation_text(prop, "EndUserText.label") or self._annotation_text(prop, "Label") or ""

                    fields.append(FieldMetadata(
                        name=name,
                        type=resolved,
                        nullable=nullable,
                        is_key=name in key_names,
                        max_length=max_len,
                        description=desc,
                    ))

                # Navigation properties -> relationships
                for nav in et.iter(f"{{{_OData_NS}}}NavigationProperty"):
                    nav_name = nav.attrib.get("Name", "")
                    nav_type = nav.attrib.get("Type", "")
                    target = nav_type.replace("Collection(", "").rstrip(")").split(".")[-1]
                    if target:
                        relationships.append(Relationship(
                            source_entity=entity_name,
                            source_field=nav_name,
                            target_entity=target,
                            target_field="",
                            cardinality="one-to-many" if "Collection" in nav_type else "many-to-one",
                        ))

                entities.append(EntityMetadata(
                    name=entity_name,
                    description=description,
                    fields=fields,
                    relationships=[r for r in relationships if r.source_entity == entity_name],
                ))

        return entities, relationships

    @staticmethod
    def _annotation_text(element: ET.Element, term_suffix: str) -> str | None:
        """Extract annotation string value from OData/SAP vocabulary annotations."""
        for ann in element.iter(f"{{{_OData_NS}}}Annotation"):
            term = ann.attrib.get("Term", "")
            if term.endswith(term_suffix):
                return ann.attrib.get("String", ann.text or "")
        return None

    @staticmethod
    def _detect_version(root: ET.Element) -> str:
        for schema in root.iter(f"{{{_OData_NS}}}Schema"):
            ns = schema.attrib.get("Namespace", "")
            if ns:
                return ns
        return "SAP OData v4"
