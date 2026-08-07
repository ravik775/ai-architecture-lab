"""User creation is internal-token-protected, not open self-signup -
mirrors `/internal/jobs`'s pattern (see `app/api/internal/auth.py`). This
sidesteps the bootstrap problem of "who's allowed to create the first
admin" by reusing the same shared secret operators already need to trigger
batch jobs, rather than building a separate first-run flow. Demo-scope
only - see `app/security/__init__.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_auth_service
from app.api.internal.auth import require_internal_token
from app.api.v1.auth_schemas import CreateUserRequest, UserOut
from app.application.auth_service import AuthService
from app.domain.errors import UserAlreadyExistsError
from app.observability.metrics import auth_requests_total

router = APIRouter(prefix="/internal/auth", tags=["internal"], dependencies=[Depends(require_internal_token)])


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(payload: CreateUserRequest, service: AuthService = Depends(get_auth_service)) -> UserOut:
    try:
        row = await service.create_user(username=payload.username, password=payload.password, role=payload.role)
    except UserAlreadyExistsError as exc:
        auth_requests_total.labels(operation="create_user", status="failure").inc()
        raise HTTPException(status_code=409, detail=f"Username already exists: {payload.username}") from exc
    auth_requests_total.labels(operation="create_user", status="success").inc()
    return UserOut(id=row.id, username=row.username, role=row.role)
