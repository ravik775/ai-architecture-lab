from __future__ import annotations

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(request: Request, response: Response) -> dict[str, str]:
    db = request.app.state.db
    try:
        async with db.session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = 503
        return {"status": "not_ready", "reason": "database_unreachable"}
    return {"status": "ready"}
