"""Turning request records into the numbers the page draws.

Specification sections 4.4 and 4.5. Both routes are thin wrappers around the two
functions here, which take plain lists of dictionaries and return plain
dictionaries — no HTTP, no application state — so the arithmetic can be tested
directly against hand-built windows.

The recurring decision in this module is what to do with nothing. An empty
window is not an error and not a zero: no requests means there is no average
response time, and reporting `0.0 ms` would draw a line at the bottom of the
chart that reads as "very fast" instead of "nothing happened". So counts fall
back to 0 and averages fall back to None, all the way through to the page, which
renders None as `-`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .logstore import is_error

# `m` is deliberately mapped to minutes. Pandas reads a bare `m` as month-end,
# so `5m` would silently become five months — an interval nobody asked for, on a
# route whose default window is seven days.
UNIT_ALIASES = {
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "m": "min", "min": "min", "mins": "min", "minute": "min", "minutes": "min",
    "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
    "d": "d", "day": "d", "days": "d",
}
UNIT_SECONDS = {"s": 1, "min": 60, "h": 3600, "d": 86400}
INTERVAL_PATTERN = re.compile(r"^\s*(\d+)\s*([a-zA-Z]+)\s*$")

# An interval finer than this over a seven-day window produces more than 20,000
# points, which no line chart can render usefully and no browser enjoys
# receiving.
MIN_INTERVAL = timedelta(seconds=30)
MAX_BUCKETS = 20_000


def parse_interval(interval: str) -> tuple[str, timedelta]:
    """`"5min"` → `("5min", timedelta(minutes=5))`. Raises ValueError otherwise.

    Returns the pandas frequency alias alongside the duration because the two
    routes need different things: resampling wants the alias, bucket-count
    validation wants the duration.
    """
    match = INTERVAL_PATTERN.match(str(interval or ""))
    if not match:
        raise ValueError(
            f"interval must look like '5min', '1h' or '1d', not {interval!r}"
        )
    amount, unit = int(match.group(1)), match.group(2).lower()
    if amount <= 0:
        raise ValueError("interval must be a positive amount of time")
    if unit not in UNIT_ALIASES:
        raise ValueError(
            f"unknown interval unit {unit!r}; use s, min, h or d"
        )
    canonical = UNIT_ALIASES[unit]
    duration = timedelta(seconds=amount * UNIT_SECONDS[canonical])
    if duration < MIN_INTERVAL:
        raise ValueError(f"interval must be at least {int(MIN_INTERVAL.total_seconds())}s")
    return f"{amount}{canonical}", duration


def _mean(values: list[float]) -> float | None:
    """A mean, or None when there is nothing to average."""
    return round(float(np.mean(values)), 4) if values else None


def summarise(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Specification 4.4 step 9 — one window's four aggregate numbers."""
    if not entries:
        return {
            "total_requests": 0,
            "avg_response_time_ms": None,
            "error_rate": None,
            "avg_probability": None,
        }
    response_times = [float(e["response_time_ms"]) for e in entries]
    probabilities = [
        float(e["probability"]) for e in entries if e.get("probability") is not None
    ]
    errors = [1.0 if is_error(e["status_code"]) else 0.0 for e in entries]
    return {
        "total_requests": len(entries),
        "avg_response_time_ms": _mean(response_times),
        "error_rate": _mean(errors),
        "avg_probability": _mean(probabilities),
    }


def delta(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    """`current − previous`, field by field.

    A field is None when either side is None (specification 3.6.3): with no
    previous window there is no change to report, and reporting the current
    value as the change would be a fabrication. ``total_requests`` is always a
    number on both sides, so its delta always exists.
    """
    result: dict[str, Any] = {}
    for key, value in current.items():
        other = previous.get(key)
        if value is None or other is None:
            result[key] = None
        else:
            result[key] = round(float(value) - float(other), 6)
    result["total_requests"] = int(current["total_requests"] - previous["total_requests"])
    return result


def timeseries(entries: list[dict[str, Any]], interval: str) -> list[dict[str, Any]]:
    """Specification 4.5 steps 8-13 — one row per time bucket.

    Buckets between the first and last request are kept even when empty:
    ``requests`` becomes 0 and the averages become None. Dropping them would
    join the line across a gap and hide an outage, which is the single most
    important thing a traffic chart has to show.
    """
    if not entries:
        return []
    alias, duration = parse_interval(interval)

    frame = pd.DataFrame(entries)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.set_index("timestamp").sort_index()
    frame["is_error"] = frame["status_code"].map(is_error).astype(float)
    if "probability" not in frame.columns:
        frame["probability"] = np.nan

    span = frame.index.max() - frame.index.min()
    if span / duration > MAX_BUCKETS:
        raise ValueError(
            f"interval {interval!r} would produce more than {MAX_BUCKETS:,} buckets "
            "over this window; use a coarser interval"
        )

    buckets = frame.resample(alias)
    aggregated = pd.DataFrame({
        "requests": buckets.size(),
        "avg_response_time_ms": buckets["response_time_ms"].mean().round(4),
        "error_rate": buckets["is_error"].mean().round(6),
        "avg_probability": buckets["probability"].mean().round(6),
    })
    # An empty bucket has no requests and therefore no average of anything. The
    # count is a real zero; the averages stay null rather than becoming one.
    aggregated["requests"] = aggregated["requests"].fillna(0).astype(int)
    aggregated.loc[aggregated["requests"] == 0, "error_rate"] = np.nan

    rows: list[dict[str, Any]] = []
    for stamp, row in aggregated.iterrows():
        rows.append({
            "timestamp": stamp.to_pydatetime().astimezone(UTC).isoformat(),
            "requests": int(row["requests"]),
            "avg_response_time_ms": None if pd.isna(row["avg_response_time_ms"])
            else float(row["avg_response_time_ms"]),
            "error_rate": None if pd.isna(row["error_rate"]) else float(row["error_rate"]),
            "avg_probability": None if pd.isna(row["avg_probability"])
            else float(row["avg_probability"]),
        })
    return rows


def isoformat(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()
