"""FastAPI application factory."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from erp_auto_mapper.api.auth import JWKSAuthProvider, NoopAuthProvider
from erp_auto_mapper.api.config import MapperSettings, get_settings
from erp_auto_mapper.api.rate_limit import RateLimiter
from erp_auto_mapper.api.routers import cdm, extract, map, validate
from erp_auto_mapper.api.session_cache import SessionCache


def create_app(settings: MapperSettings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="ERP Auto Mapper",
        description="AI-powered ERP-to-CDM field mapping engine",
        version="0.1.0",
    )

    if settings.auth_disabled:
        app.state.auth_provider = NoopAuthProvider()
    else:
        app.state.auth_provider = JWKSAuthProvider(settings)

    app.state.rate_limiter = RateLimiter(
        max_fields_per_request=settings.rate_limit_fields_per_request,
        max_requests_per_day=settings.rate_limit_requests_per_day,
    )

    app.state.session_cache = SessionCache(ttl_seconds=settings.session_ttl_seconds)

    app.include_router(map.router)
    app.include_router(validate.router)
    app.include_router(extract.router)
    app.include_router(cdm.router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def serve_cli() -> None:
    settings = get_settings()
    uvicorn.run(
        "erp_auto_mapper.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=False,
    )
