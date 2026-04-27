"""NetSuite SuiteQL / REST schema extractor via metadata-catalog."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
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

_NS_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "decimal",
    "boolean": "boolean",
    "date": "date",
    "datetime": "datetime",
    "currency": "decimal",
    "float": "float",
    "percent": "decimal",
    "email": "string",
    "phone": "string",
    "url": "string",
    "textarea": "string",
    "richtext": "string",
    "select": "string",
    "multiselect": "string",
}


class NetSuiteExtractor(BaseERPExtractor):
    """Extract schema from NetSuite via REST metadata-catalog (JSON Schema)."""

    def __init__(self, config: ERPConnectionConfig) -> None:
        super().__init__(config)
        self._account_id: str = config.extra.get("account_id", "")

    @property
    def erp_type(self) -> ERPType:
        return ERPType.NETSUITE

    async def extract(self) -> ERPMetadata:
        record_types = await self._fetch_record_types()
        entities: list[EntityMetadata] = []

        for rt in record_types:
            rt_name = rt.get("name", "")
            try:
                entity = await self._fetch_record_schema(rt_name, rt.get("href", ""))
                entities.append(entity)
            except Exception:
                logger.warning("Failed to extract NetSuite record: %s", rt_name, exc_info=True)

        return ERPMetadata(
            source=ERPType.NETSUITE,
            source_version="REST 2023.2",
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            entities=entities,
            raw_config={"account_id": self._account_id},
        )

    async def extract_sample_values(
        self, entity: str, fields: list[str], limit: int = 5
    ) -> dict[str, list[Any]]:
        url = f"{self.config.base_url}/record/v1/{entity}?limit={limit}"
        data = await self._request_json(url)
        result: dict[str, list[Any]] = {f: [] for f in fields}
        for item in data.get("items", []):
            for f in fields:
                if f in item:
                    result[f].append(item[f])
        return result

    async def health_check(self) -> bool:
        url = f"{self.config.base_url}/record/v1/metadata-catalog/"
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
        headers = self._build_auth_headers("GET", self.config.base_url)
        headers["Accept"] = "application/json"
        return httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(self.config.timeout_seconds),
            follow_redirects=True,
        )

    def _build_auth_headers(self, method: str, url: str) -> dict[str, str]:
        """Build OAuth 1.0 TBA headers for NetSuite."""
        creds = self.config.extra
        consumer_key = creds.get("consumer_key", "")
        consumer_secret = creds.get("consumer_secret", "")
        token_id = creds.get("token_id", "")
        token_secret = creds.get("token_secret", "")
        nonce = hashlib.sha256(str(time.time()).encode()).hexdigest()[:20]
        timestamp = str(int(time.time()))

        base_string = f"{method.upper()}&{url}&oauth_consumer_key={consumer_key}&oauth_nonce={nonce}&oauth_timestamp={timestamp}&oauth_token={token_id}"
        signing_key = f"{consumer_secret}&{token_secret}"
        signature = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha256).hexdigest()

        auth_header = (
            f'OAuth realm="{self._account_id}",'
            f'oauth_consumer_key="{consumer_key}",'
            f'oauth_token="{token_id}",'
            f'oauth_nonce="{nonce}",'
            f'oauth_timestamp="{timestamp}",'
            f'oauth_signature_method="HMAC-SHA256",'
            f'oauth_version="1.0",'
            f'oauth_signature="{signature}"'
        )
        return {"Authorization": auth_header}

    async def _request_json(self, url: str) -> dict[str, Any]:
        headers = self._build_auth_headers("GET", url)
        headers["Accept"] = "application/json"
        async with httpx.AsyncClient(
            headers=headers, timeout=httpx.Timeout(self.config.timeout_seconds)
        ) as client:
            for attempt in range(self.config.max_retries):
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.json()  # type: ignore[no-any-return]
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        wait = int(exc.response.headers.get("Retry-After", 2 ** attempt))
                        logger.info("NetSuite rate-limited, waiting %ds", wait)
                        await asyncio.sleep(wait)
                        continue
                    logger.warning("NetSuite request attempt %d: %s", attempt + 1, exc)
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                except httpx.TimeoutException:
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"NetSuite request failed after retries: {url}")

    async def _fetch_record_types(self) -> list[dict[str, Any]]:
        url = f"{self.config.base_url}/record/v1/metadata-catalog/"
        data = await self._request_json(url)
        items: list[dict[str, Any]] = []
        for link in data.get("links", []):
            if link.get("rel") == "recordType":
                items.append({"name": link.get("name", ""), "href": link.get("href", "")})
        return items

    async def _fetch_record_schema(self, name: str, href: str) -> EntityMetadata:
        url = href or f"{self.config.base_url}/record/v1/metadata-catalog/{name}"
        schema = await self._request_json(url)
        fields: list[FieldMetadata] = []
        relationships: list[Relationship] = []

        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))

        for field_name, field_def in properties.items():
            raw_type = field_def.get("type", "string")
            if isinstance(raw_type, list):
                raw_type = next((t for t in raw_type if t != "null"), "string")
            resolved = _NS_TYPE_MAP.get(raw_type, self._normalize_type(raw_type))

            enum_vals: list[str] = []
            if "enum" in field_def:
                enum_vals = [str(v) for v in field_def["enum"][:50]]

            # Custom fields start with 'custbody', 'custcol', etc.
            desc = field_def.get("title", "")
            if field_name.startswith(("custbody", "custcol", "custitem", "custevent")):
                desc = f"[Custom] {desc}" if desc else f"[Custom Field] {field_name}"

            # Reference -> relationship
            ref = field_def.get("$ref", "") or field_def.get("x-ns-recordRef", "")
            if ref:
                target = ref.split("/")[-1]
                relationships.append(Relationship(
                    source_entity=name,
                    source_field=field_name,
                    target_entity=target,
                    target_field="id",
                    cardinality="many-to-one",
                ))

            fields.append(FieldMetadata(
                name=field_name,
                type=resolved,
                nullable=field_name not in required_fields,
                is_key=(field_name == "id"),
                description=desc,
                enum_values=enum_vals,
            ))

        # Sublists (line items)
        for sublist_name, sublist_def in schema.get("x-ns-sublists", {}).items():
            sub_props = sublist_def.get("properties", {})
            for sf_name, sf_def in sub_props.items():
                sf_type = sf_def.get("type", "string")
                if isinstance(sf_type, list):
                    sf_type = next((t for t in sf_type if t != "null"), "string")
                fields.append(FieldMetadata(
                    name=f"{sublist_name}.{sf_name}",
                    type=_NS_TYPE_MAP.get(sf_type, self._normalize_type(sf_type)),
                    nullable=True,
                    description=f"Sublist: {sublist_name} / {sf_def.get('title', sf_name)}",
                ))

        return EntityMetadata(
            name=name,
            description=schema.get("title", ""),
            fields=fields,
            relationships=relationships,
        )
