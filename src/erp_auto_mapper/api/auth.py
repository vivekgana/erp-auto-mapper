"""Pluggable OAuth2 authentication middleware with JWKS support."""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol, runtime_checkable

import httpx
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from erp_auto_mapper.api.config import MapperSettings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


@runtime_checkable
class AuthProvider(Protocol):
    async def validate_token(self, token: str) -> dict[str, Any]: ...


class JWKSAuthProvider:
    """Validates JWTs using JWKS endpoint with caching and hard timeout."""

    def __init__(self, settings: MapperSettings) -> None:
        self._jwks_url = settings.auth_jwks_url
        self._audience = settings.auth_audience
        self._issuer = settings.auth_issuer
        self._cache_ttl = settings.auth_jwks_cache_ttl
        self._timeout = settings.auth_jwks_timeout
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_cached_at: float = 0.0

    async def _get_jwks(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._jwks_cache and (now - self._jwks_cached_at) < self._cache_ttl:
            return self._jwks_cache

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(self._jwks_url)
                resp.raise_for_status()
                self._jwks_cache = resp.json()
                self._jwks_cached_at = now
                return self._jwks_cache
        except Exception:
            if self._jwks_cache:
                logger.warning("JWKS refresh failed, using cached keys")
                return self._jwks_cache
            raise HTTPException(status_code=503, detail="Authentication service unavailable")

    async def validate_token(self, token: str) -> dict[str, Any]:
        from jose import JWTError, jwt as jose_jwt

        jwks = await self._get_jwks()
        try:
            header = jose_jwt.get_unverified_header(token)
        except JWTError:
            raise HTTPException(status_code=401, detail="Malformed token")

        kid = header.get("kid")
        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = k
                break
        if not key:
            raise HTTPException(status_code=401, detail="Token signing key not found")

        try:
            payload = jose_jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer or None,
            )
            return dict(payload)
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")


class NoopAuthProvider:
    """Auth bypass for development / testing."""

    async def validate_token(self, token: str) -> dict[str, Any]:
        return {"sub": "dev-user", "tenant_id": "dev-tenant"}


async def get_current_user(request: Request) -> dict[str, Any]:
    provider: AuthProvider = request.app.state.auth_provider
    credentials: HTTPAuthorizationCredentials | None = await security(request)
    if credentials is None:
        if isinstance(provider, NoopAuthProvider):
            return await provider.validate_token("")
        raise HTTPException(status_code=401, detail="Missing authorization header")
    return await provider.validate_token(credentials.credentials)
