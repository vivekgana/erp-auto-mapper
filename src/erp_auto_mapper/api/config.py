"""API configuration — all settings sourced from MAPPER_* environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class MapperSettings(BaseSettings):
    model_config = {"env_prefix": "MAPPER_"}

    auth_disabled: bool = False
    auth_jwks_url: str = ""
    auth_audience: str = "erp-auto-mapper"
    auth_issuer: str = ""
    auth_jwks_cache_ttl: int = 300
    auth_jwks_timeout: float = 2.0

    llm_endpoint: str = ""
    llm_api_key: str = ""
    llm_max_parallel: int = 10
    llm_timeout: float = 30.0

    rate_limit_fields_per_request: int = 50
    rate_limit_requests_per_day: int = 100

    session_ttl_seconds: int = 3600

    host: str = "0.0.0.0"
    port: int = 8000


def get_settings() -> MapperSettings:
    return MapperSettings()
