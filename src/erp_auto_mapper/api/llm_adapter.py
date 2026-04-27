"""httpx-backed LLMCallable with parallel batching."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HttpxLLMCallable:
    """Async LLM callable that batches requests with controlled parallelism."""

    def __init__(
        self,
        endpoint: str,
        api_key: str = "",
        max_parallel: int = 10,
        timeout: float = 30.0,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._timeout = timeout

    async def __call__(self, prompt: str) -> str:
        if not self._endpoint:
            return "{}"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.1,
        }

        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self._endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return str(choices[0].get("message", {}).get("content", "{}"))
                return "{}"

    async def batch_call(self, prompts: list[str]) -> list[str]:
        tasks = [self(p) for p in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r if isinstance(r, str) else "{}" for r in results]
