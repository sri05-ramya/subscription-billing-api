"""Runs around every request: request ID, timing, one log line, safe 500 errors."""

import logging
import re
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.logging_config import request_id_var

logger = logging.getLogger("app.requests")
SAFE_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
SLOW_MS = 500  # requests slower than this are logged as warnings


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Tracking number: reuse a safe one sent by the caller, or make a new one
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if SAFE_ID.match(incoming) else uuid.uuid4().hex[:12]
        token = request_id_var.set(request_id)

        # 2. Start the stopwatch
        start = time.perf_counter()
        try:
            # 3. Let the request go to the endpoint
            response = await call_next(request)
        except Exception:
            # 6. Something crashed: log the full error, return a clean 500
            logger.exception("unhandled error", extra={"method": request.method, "path": request.url.path})
            response = JSONResponse(
                status_code=500,
                content={"error": {"code": "internal_error", "message": "Something went wrong", "request_id": request_id}},
            )

        # 4. One log line per request
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        level = logging.WARNING if duration_ms > SLOW_MS else logging.INFO
        logger.log(
            level,
            "request finished",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        # 5. Give the tracking number and timing back to the caller
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = str(duration_ms)
        request_id_var.reset(token)
        return response