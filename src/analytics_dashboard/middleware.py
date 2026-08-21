"""The HTTP middleware that produces every number on the Analytics page.

Specification section 4.2. Three properties matter:

**It observes; it does not participate.** Recording happens in a ``finally``
block and the store swallows its own failures, so a broken log entry costs an
observation and never a response. An observability layer that can fail a
request is worse than no observability layer.

**It counts what happened, including the failures.** A request that raised is
logged as a 500 before the exception continues on its way. Dropping it would
make the error-rate chart — the one thing on the page that exists to show
failures — go quiet exactly when the service starts failing.

**It does not count itself.** Requests to ``/analytics/*`` are excluded, because
otherwise every dashboard refresh inflates the request count it is about to
render, and a page left open on a wall display becomes the busiest client of
the service it is monitoring.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .config import EXCLUDED_PATHS, EXCLUDED_PREFIXES
from .logstore import RequestLogStore


def is_excluded(path: str) -> bool:
    return path in EXCLUDED_PATHS or path.startswith(EXCLUDED_PREFIXES)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Time every business request and append one entry per call."""

    def __init__(self, app, store: RequestLogStore) -> None:
        super().__init__(app)
        self.store = store

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if is_excluded(path):
            return await call_next(request)

        started = time.perf_counter()
        stamp = datetime.now(UTC)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except HTTPException as exc:
            # FastAPI normally converts these to responses below this layer, so
            # reaching here means something re-raised. Record the status the
            # caller will actually see, then let it continue.
            status_code = exc.status_code
            raise
        except Exception:
            status_code = 500
            raise
        finally:
            # Written after the response is produced, so `request.state` already
            # carries whatever the route put there (specification 4.3).
            state = request.scope.get("state") or {}
            self.store.record(
                endpoint=path,
                status_code=status_code,
                response_time_ms=(time.perf_counter() - started) * 1000,
                timestamp=stamp,
                probability=state.get("probability"),
                model_version=state.get("model_version"),
            )
