from __future__ import annotations

from fastapi import Header, HTTPException, Request


async def require_internal_token(request: Request, x_internal_token: str | None = Header(None)) -> None:
    expected = request.app.state.settings.security.internal_api_token
    if not x_internal_token or x_internal_token != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Internal-Token")
