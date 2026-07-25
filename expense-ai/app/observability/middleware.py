import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.context import reset_request_id, set_request_id
from app.observability.logging import log_info


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        token = set_request_id(request_id)
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_info("http.request.completed", method=request.method, path=request.url.path, latency_ms=latency_ms)
            reset_request_id(token)