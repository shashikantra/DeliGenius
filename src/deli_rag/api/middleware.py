from __future__ import annotations

import logging
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("deli_rag.api")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = getattr(request.state, "request_id", "unknown")
        try:
            return await call_next(request)
        except Exception as e:
            log.exception("unhandled error request_id=%s", rid)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "internal_server_error",
                    "detail": str(e),
                    "request_id": rid,
                },
            )


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        import time
        rid = getattr(request.state, "request_id", "unknown")
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000
        log.info(
            "%s %s -> %d in %.1fms request_id=%s",
            request.method, request.url.path, response.status_code, ms, rid,
        )
        return response