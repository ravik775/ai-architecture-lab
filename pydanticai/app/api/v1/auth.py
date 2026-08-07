from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_auth_service, get_current_claims
from app.api.v1.auth_schemas import LoginRequest, MeOut, TokenOut
from app.application.auth_service import AuthService
from app.domain.errors import InvalidCredentialsError
from app.observability.metrics import auth_requests_total

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)) -> TokenOut:
    try:
        token, expires_in, role = await service.login(username=payload.username, password=payload.password)
    except InvalidCredentialsError as exc:
        auth_requests_total.labels(operation="login", status="failure").inc()
        raise HTTPException(status_code=401, detail="Invalid username or password") from exc
    auth_requests_total.labels(operation="login", status="success").inc()
    return TokenOut(access_token=token, expires_in_seconds=expires_in, role=role)


@router.get("/me", response_model=MeOut)
async def me(claims: dict = Depends(get_current_claims)) -> MeOut:
    return MeOut(username=claims["sub"], role=claims["role"])
