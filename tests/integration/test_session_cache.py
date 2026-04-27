"""Integration tests for SessionCache — TTL and tenant isolation."""

import time

from erp_auto_mapper.api.session_cache import SessionCache


def test_put_and_get():
    cache = SessionCache(ttl_seconds=60)
    cache.put("tenant-a", "eng-1", {"result": "ok"})
    data = cache.get("tenant-a", "eng-1")
    assert data == {"result": "ok"}


def test_tenant_isolation():
    cache = SessionCache(ttl_seconds=60)
    cache.put("tenant-a", "eng-1", {"a": 1})
    cache.put("tenant-b", "eng-1", {"b": 2})
    assert cache.get("tenant-a", "eng-1") == {"a": 1}
    assert cache.get("tenant-b", "eng-1") == {"b": 2}


def test_ttl_expiry():
    cache = SessionCache(ttl_seconds=1)
    cache.put("t", "e", {"data": True})
    assert cache.get("t", "e") is not None
    time.sleep(1.1)
    assert cache.get("t", "e") is None


def test_evict_expired():
    cache = SessionCache(ttl_seconds=1)
    cache.put("a", "1", {})
    cache.put("b", "2", {})
    time.sleep(1.1)
    evicted = cache.evict_expired()
    assert evicted == 2
