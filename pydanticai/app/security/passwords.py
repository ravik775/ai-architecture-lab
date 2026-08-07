"""Password hashing via `hashlib.pbkdf2_hmac` - stdlib only, no bcrypt/
passlib dependency for what's a demo-scope credential store (see
`app/security/__init__.py`). PBKDF2-HMAC-SHA256, 100k iterations, a fresh
16-byte salt per password: slower to brute-force than a bare hash, but
still weaker than bcrypt/argon2's memory-hardness - acceptable here, not
for a real multi-tenant deployment.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 100_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations_str, salt, expected_hex = stored.split("$", 3)
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations_str))
    return hmac.compare_digest(digest.hex(), expected_hex)
