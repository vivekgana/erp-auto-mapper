"""ModelServingLLMCallable — LLM via Databricks Model Serving endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ModelServingLLMCallable:
    """Async LLM callable backed by Databricks Model Serving."""

    def __init__(
        self,
        host: str = "",
        token: str = "",
        endpoint_name: str = "erp-auto-mapper-llm",
        max_parallel: int = 10,
    ) -> None:
        self._host = host
        self._token = token
        self._endpoint_name = endpoint_name
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._ws: Any = None

    def _get_workspace(self) -> Any:
        if self._ws is None:
            from databricks.sdk import WorkspaceClient
            self._ws = WorkspaceClient(host=self._host, token=self._token)
        return self._ws

    async def __call__(self, prompt: str) -> str:
        async with self._semaphore:
            ws = self._get_workspace()
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: ws.serving_endpoints.query(
                    name=self._endpoint_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                    temperature=0.1,
                ),
            )
            choices = getattr(response, "choices", [])
            if choices:
                msg = getattr(choices[0], "message", None)
                return getattr(msg, "content", "{}") if msg else "{}"
            return "{}"
