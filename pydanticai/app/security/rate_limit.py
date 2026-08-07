"""IP-based rate limiting - a fixed 60s sliding window per client IP,
enforced at the ASGI middleware layer.

In-memory, per-process: fine for this app's documented single-replica scope
(see README's Known limitations) - would need a shared store (Redis, etc.)
to work correctly behind >1 replica or worker process, since each process
would otherwise enforce its own independent limit.

Client IP is taken from `X-Forwarded-For`'s first hop if present, else the
raw ASGI transport address. Trusting XFF is only safe behind a reverse
proxy that overwrites/strips client-supplied XFF, which this app does not
verify - a documented gap, consistent with this app's minimal-security demo
scope (see SecuritySettings' docstring notes).
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.observability.metrics import rate_limit_rejections_total
from app.observability.sampling import HEALTH_CHECK_ROUTES

WINDOW_SECONDS = 60.0

# NiceGUI is mounted at "/ui" (app/ui/pages.py); a single page load fires
# a burst of 15+ background requests for it (static JS/CSS/font assets,
# the socket.io client, per-component asset routes) - verified live via
# the app's own request-completion logs. None of that is user-driven API
# traffic the rate limiter is meant to police, and 10/min would make the
# UI itself unusable after one page load. Some of NiceGUI's shared static
# assets are registered on the FastAPI app directly under "/_nicegui" too
# (outside the "/ui" mount path) - both prefixes are exempt for the same
# reason health-check routes are.
_RATE_LIMIT_EXEMPT_PREFIXES = ("/ui", "/_nicegui")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class IPRateLimitMiddleware(BaseHTTPMiddleware):
    """Reads `request.app.state.settings.security` per-request (not a
    constructor arg) so it always reflects whatever settings the app was
    built with - same pattern as `require_internal_token`. Route matching
    hasn't happened yet when `dispatch` starts (this middleware wraps the
    router), so health-check exemption and rejection accounting both use
    the raw request path rather than a route template."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        security = request.app.state.settings.security
        path = request.url.path
        if (
            not security.rate_limit_enabled
            or path in HEALTH_CHECK_ROUTES
            or path.startswith(_RATE_LIMIT_EXEMPT_PREFIXES)
        ):
            return await call_next(request)

        ip = _client_ip(request)
        now = time.monotonic()
        hits = self._hits[ip]
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()

        if len(hits) >= security.rate_limit_requests_per_minute:
            rate_limit_rejections_total.inc()
            retry_after = max(1, int(WINDOW_SECONDS - (now - hits[0])))
            return Response(
                content='{"detail": "Rate limit exceeded. Try again later."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        return await call_next(request)
