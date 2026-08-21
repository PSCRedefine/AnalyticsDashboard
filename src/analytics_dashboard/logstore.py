"""The in-memory request log the dashboard reads.

Specification section 4.2. Everything the Analytics page shows is derived from
this buffer, which means two properties matter more than anything else about it:

**It must never break a request.** The log exists to observe the service, not to
be part of it. Recording is wrapped so that a malformed entry costs an
observation, never a response.

**It must be honest about what it holds.** Entries recorded by the middleware
are real traffic. Entries injected by the backfill tool are not, and the store
tracks the difference so that ``source`` on the page says which it is. A
dashboard whose Data Source field is a constant string is a dashboard that
cannot tell you it is showing you a demo.

The buffer is a ``deque`` with a maximum length: bounded memory, and the oldest
entry falls out rather than the newest, so a burst cannot blind the page to what
is happening right now. It does not survive a restart, which is the accepted
cost of not having a time-series database in this specification.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from .config import LOG_CAPACITY

logger = logging.getLogger(__name__)

REAL_SOURCE = "in_memory_api_logs"
MIXED_SOURCE = "in_memory_api_logs+synthetic_backfill"
STATUS_FAMILIES = ("2xx", "3xx", "4xx", "5xx")


def status_family(status_code: int) -> str:
    """`200` → `2xx`. Anything outside 100–599 is reported as `other`."""
    hundreds = int(status_code) // 100
    return f"{hundreds}xx" if 1 <= hundreds <= 5 else "other"


def is_error(status_code: int) -> bool:
    """Specification 4.5 step 10: anything that is not a 2xx counts as an error.

    A 404 is the caller's mistake and a 500 is ours, but the error-rate chart is
    a health signal, and a service suddenly returning 404 to everything is not
    healthy. The two are separable through the `status_code_family` filter when
    someone needs to separate them.
    """
    return not 200 <= int(status_code) < 300


class RequestLogStore:
    """A bounded, thread-safe ring buffer of request records.

    Uvicorn serves from a thread pool, so ``record`` can be called concurrently.
    ``deque.append`` is atomic under CPython, but the synthetic counter beside it
    is not, so both live under one lock. The lock is held for an append and a
    list copy, never across a computation.
    """

    def __init__(self, capacity: int = LOG_CAPACITY) -> None:
        self._entries: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self.capacity = capacity

    def __len__(self) -> int:
        return len(self._entries)

    def record(
        self,
        *,
        endpoint: str,
        status_code: int,
        response_time_ms: float,
        timestamp: datetime | None = None,
        probability: float | None = None,
        model_version: str | None = None,
        synthetic: bool = False,
    ) -> None:
        """Append one entry. Never raises.

        The four required fields come from the middleware; ``probability`` and
        ``model_version`` come from ``request.state`` and are present only for
        prediction routes (specification 4.3).
        """
        try:
            entry = {
                "timestamp": (timestamp or datetime.now(UTC)).astimezone(UTC),
                "endpoint": str(endpoint),
                "status_code": int(status_code),
                "response_time_ms": round(float(response_time_ms), 3),
            }
            if probability is not None:
                entry["probability"] = float(probability)
            if model_version is not None:
                entry["model_version"] = str(model_version)
            if synthetic:
                entry["synthetic"] = True
            with self._lock:
                self._entries.append(entry)
        except Exception as exc:  # noqa: BLE001 - observing must not break serving
            logger.warning("dropped a request log entry: %s", exc)

    def extend(self, entries: Iterable[dict[str, Any]]) -> int:
        """Bulk-append pre-built entries. Used by the backfill tool only."""
        count = 0
        for entry in entries:
            self.record(**entry)
            count += 1
        return count

    def snapshot(self) -> list[dict[str, Any]]:
        """A stable copy, so aggregation is not racing new arrivals."""
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def last_updated(self) -> datetime:
        """The newest entry's timestamp, or now when the buffer is empty.

        Specification 2.2: this field tells the reader how stale the page is.
        Falling back to now on an empty buffer is right — there is no data, and
        the absence is current.
        """
        entries = self.snapshot()
        return max((e["timestamp"] for e in entries), default=datetime.now(UTC))

    def select(
        self,
        start: datetime,
        end: datetime,
        endpoint: str | None = None,
        model_version: str | None = None,
        status_code_family: str | None = None,
    ) -> list[dict[str, Any]]:
        """Entries in ``[start, end)`` matching every filter that was supplied.

        Half-open on purpose: consecutive windows tile without double-counting
        the boundary, which matters because the summary route compares a window
        against the one immediately before it.
        """
        selected = []
        for entry in self.snapshot():
            stamp = entry["timestamp"]
            if not start <= stamp < end:
                continue
            if endpoint and entry["endpoint"] != endpoint:
                continue
            if model_version and entry.get("model_version") != model_version:
                continue
            if status_code_family and status_family(entry["status_code"]) != status_code_family:
                continue
            selected.append(entry)
        return selected

    def source(self, entries: Iterable[dict[str, Any]] | None = None) -> str:
        """What the Data Source field should say for these entries.

        The page's stated purpose for this field is telling the reader whether
        they are looking at real traffic. It only does that if it can say no.
        """
        rows = self.snapshot() if entries is None else entries
        return MIXED_SOURCE if any(e.get("synthetic") for e in rows) else REAL_SOURCE


def resolve_window(
    start: datetime | None, end: datetime | None, days: int
) -> tuple[datetime, datetime]:
    """Specification 4.4 steps 2-3: default the end to now and the start to now − N days."""
    end = end or datetime.now(UTC)
    start = start or (end - timedelta(days=days))
    return start, end
