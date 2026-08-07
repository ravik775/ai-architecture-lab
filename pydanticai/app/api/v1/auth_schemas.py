from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["user", "trace_admin"]


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)
    role: Role = "user"


class UserOut(BaseModel):
    id: int
    username: str
    role: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    role: str


class MeOut(BaseModel):
    username: str
    role: str
