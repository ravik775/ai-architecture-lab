"""Demo-grade security: IP rate limiting, password hashing, JWT issuance.

Everything here is deliberately minimal - see each module's docstring for
its specific trade-offs. This is a single-user/local-demo app; none of this
is hardened for a real multi-tenant deployment (no key rotation, no token
revocation, no distributed rate-limit store).
"""
from __future__ import annotations
