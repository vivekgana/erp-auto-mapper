"""In-memory rate limiter — fields per request and requests per day per tenant."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException


class RateLimiter:
    def __init__(self, max_fields_per_request: int = 50, max_requests_per_day: int = 100) -> None:
        self._max_fields = max_fields_per_request
        self._max_requests = max_requests_per_day
        self._counters: dict[str, list[float]] = defaultdict(list)

    def check_field_count(self, field_count: int) -> None:
        if field_count > self._max_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Free tier limit: max {self._max_fields} fields per request, got {field_count}",
            )

    def check_request_count(self, tenant_id: str) -> None:
        now = time.time()
        day_ago = now - 86400
        timestamps = self._counters[tenant_id]
        self._counters[tenant_id] = [t for t in timestamps if t > day_ago]
        if len(self._counters[tenant_id]) >= self._max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: max {self._max_requests} requests per day",
            )
        self._counters[tenant_id].append(now)
