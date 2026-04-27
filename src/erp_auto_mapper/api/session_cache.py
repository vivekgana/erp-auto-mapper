"""TTL session cache keyed by (tenant_id, engagement_id)."""

from __future__ import annotations

import time
from typing import Any


class SessionCache:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, dict[str, Any]]] = {}

    def _key(self, tenant_id: str, engagement_id: str) -> str:
        return f"{tenant_id}::{engagement_id}"

    def get(self, tenant_id: str, engagement_id: str) -> dict[str, Any] | None:
        k = self._key(tenant_id, engagement_id)
        entry = self._store.get(k)
        if entry is None:
            return None
        ts, data = entry
        if time.time() - ts > self._ttl:
            del self._store[k]
            return None
        return data

    def put(self, tenant_id: str, engagement_id: str, data: dict[str, Any]) -> None:
        k = self._key(tenant_id, engagement_id)
        self._store[k] = (time.time(), data)

    def evict_expired(self) -> int:
        now = time.time()
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            del self._store[k]
        return len(expired)
