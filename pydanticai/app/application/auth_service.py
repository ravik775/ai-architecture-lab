"""User creation + login. Thin orchestration over `UserRepository` +
`app/security/*` - see those modules for the actual hashing/JWT mechanics.
"""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.config.settings import SecuritySettings
from app.domain.errors import InvalidCredentialsError, UserAlreadyExistsError
from app.infrastructure.database.models import UserRow
from app.infrastructure.database.repositories import UserRepository
from app.infrastructure.database.session import Database
from app.security.jwt_tokens import create_access_token
from app.security.passwords import hash_password, verify_password


class AuthService:
    def __init__(self, db: Database, repository: UserRepository, security_settings: SecuritySettings) -> None:
        self._db = db
        self._repository = repository
        self._settings = security_settings

    async def create_user(self, *, username: str, password: str, role: str) -> UserRow:
        async with self._db.session() as session:
            try:
                row = await self._repository.create_user(
                    session, username=username, password_hash=hash_password(password), role=role
                )
                await session.commit()
            except IntegrityError as exc:
                raise UserAlreadyExistsError(username) from exc
            return row

    async def bootstrap_default_user(self) -> None:
        """Called once at startup (see main.py's lifespan). No-op unless
        both `bootstrap_admin_username`/`_password` are set - there is no
        default user otherwise. Idempotent across restarts: an existing
        username is left untouched (not re-created, not password-reset),
        so this is safe to leave configured permanently in `.env`."""
        username = self._settings.bootstrap_admin_username
        password = self._settings.bootstrap_admin_password
        if not username or not password:
            return
        try:
            await self.create_user(username=username, password=password, role=self._settings.bootstrap_admin_role)
        except UserAlreadyExistsError:
            pass

    async def login(self, *, username: str, password: str) -> tuple[str, int, str]:
        """Returns (access_token, expires_in_seconds, role)."""
        async with self._db.session() as session:
            row = await self._repository.get_by_username(session, username)
        if row is None or not verify_password(password, row.password_hash):
            raise InvalidCredentialsError
        token, expires_in = create_access_token(username=row.username, role=row.role, settings=self._settings)
        return token, expires_in, row.role
