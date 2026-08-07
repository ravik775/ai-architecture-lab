"""One pooled httpx.AsyncClient for the whole process (weather-app only -
LiteLLM Proxy calls go through PydanticAI's own client, not this one).
"""
from __future__ import annotations

import httpx

from app.config.settings import HttpClientSettings


def create_http_client(settings: HttpClientSettings) -> httpx.AsyncClient:
    timeout = httpx.Timeout(
        connect=settings.connect_timeout_seconds,
        read=settings.read_timeout_seconds,
        write=settings.write_timeout_seconds,
        pool=settings.pool_timeout_seconds,
    )
    limits = httpx.Limits(
        max_connections=settings.max_connections,
        max_keepalive_connections=settings.max_keepalive_connections,
    )
    return httpx.AsyncClient(timeout=timeout, limits=limits, http2=settings.http2)


async def close_http_client(client: httpx.AsyncClient) -> None:
    await client.aclose()
