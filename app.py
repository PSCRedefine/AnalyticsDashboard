"""Streamlit console for the Analytics Dashboard.

Specification section 2. The page answers five questions in the order an
operator asks them: has the service been called, is the call volume moving, are
responses slowing down, are errors rising, and has the model's output
distribution shifted.

It holds no state and computes no aggregate. Both endpoints return numbers that
are already final, which is deliberate — the KPI cards and the charts have to
agree, and the only way to guarantee that is for them to come from one place
that did the arithmetic once.

Nulls are load-bearing here. An empty window has no average response time, and
drawing `0.0 ms` would put a line at the bottom of the chart that reads as "very
fast" rather than "nothing happened". Every formatter below renders None as `-`.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_BASE_URL = os.getenv("ANALYTICS_API_URL", "http://127.0.0.1:8000").rstrip("/")

REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_WINDOW_DAYS = 7
DEFAULT_INTERVAL = "1h"

# Specification 3.5. Same numbers as the service's config; repeated here because
# the page is the thing that draws the banner.
ERROR_RATE_ALERT = 0.02
RESPONSE_TIME_ALERT_MS = 300.0
PROBABILITY_DRIFT_ALERT = 0.1

st.set_page_config(page_title="RankShift Serving", page_icon="🎯", layout="wide")


def call_api(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch one endpoint, returning every failure as data rather than raising."""
    url = f"{API_BASE_URL}/{path.lstrip('/')}"
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.ConnectionError:
        return {"error": "API server is offline"}
    except requests.exceptions.Timeout:
        return {"error": "Request timeout"}
    except requests.exceptions.RequestException as exc:
        return {"error": f"Error: {exc}"}
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        return {"error": f"API Error: {response.status_code} — {detail}"}
    try:
        return response.json()
    except ValueError:
        return {"error": "Error: the server returned a response that is not JSON"}


def failure(payload: dict[str, Any]) -> str | None:
    return payload.get("error") if isinstance(payload, dict) else None


def number(value: Any, pattern: str, scale: float = 1.0) -> str:
    """Format a value, or `-` when there is nothing to format (specification 3.6.3)."""
    if value is None:
        return "-"
    try:
        return pattern.format(float(value) * scale)
    except (TypeError, ValueError):
        return "-"


def show_metric(column, label: str, value: Any, change: Any, pattern: str,
                delta_pattern: str, scale: float = 1.0, inverse: bool = False) -> None:
    """One KPI card.

    ``delta`` is omitted entirely when the previous window had no data, rather
    than shown as zero: no comparison and no change are different statements,
    and `0` would claim the second when the truth is the first.

    ``inverse`` marks the metrics where up is bad. A rising error rate drawn in
    green is a dashboard actively working against its reader.
    """
    column.metric(
        label,
        number(value, pattern, scale),
        delta=None if change is None else number(change, delta_pattern, scale),
        delta_color="inverse" if inverse else "normal",
    )


def line_chart(frame: pd.DataFrame, column: str, title: str,
               y_title: str, y_range: tuple[float, float] | None = None) -> None:
    """One trend chart. Gaps in the data stay gaps."""
    figure = px.line(frame, x="timestamp", y=column, markers=True, title=title)
    figure.update_traces(line_color="#5b9bd5", marker=dict(size=5))
    figure.update_layout(
        height=280,
        margin=dict(l=10, r=10, t=48, b=10),
        xaxis_title=None,
        yaxis_title=y_title,
        showlegend=False,
    )
    if y_range:
        figure.update_yaxes(range=list(y_range))
    st.plotly_chart(figure, width="stretch")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

health = call_api("health")
with st.sidebar:
    st.header("🎛️ Controls")
    if failure(health):
        st.error(f"❌ API Status: {failure(health)}")
    else:
        st.success(f"✅ API Status: {str(health.get('status', 'unknown')).title()}")
        st.metric("Uptime", f"{float(health.get('uptime_seconds', 0)):.0f}s")
        st.caption(
            f"{int(health.get('logged_requests', 0)):,} requests in the log "
            f"(capacity {int(health.get('log_capacity', 0)):,})"
        )
    st.divider()
    page = st.selectbox("Select Page", ["Analytics Dashboard"])

st.title("📈 Analytics Dashboard")

# Specification 3.1: the window is computed on entry, with no controls to click.
# The two requests share it, so the cards and the charts describe the same span.
end = datetime.now(UTC)
start = end - timedelta(days=DEFAULT_WINDOW_DAYS)
window = {"start": start.isoformat(), "end": end.isoformat()}

summary = call_api("analytics/summary", params=window)
if failure(summary):
    st.error(f"Data source unavailable: {failure(summary)}")
    st.caption("Start the API, then reload this page.")
    st.stop()

series = call_api("analytics/timeseries", params={**window, "interval": DEFAULT_INTERVAL})
if failure(series):
    st.error(f"Data source unavailable: {failure(series)}")
    st.caption("Start the API, then reload this page.")
    st.stop()

current = summary.get("current") or {}
change = summary.get("delta") or {}
previous = summary.get("previous") or {}

# Specification 3.6.3: with no previous window there is no change to report.
# The server nulls the three averages already; `total_requests` is an int on
# both sides, so its delta always computes — and `+0` against a window that
# never existed is a comparison the reader did not make.
if not previous.get("total_requests"):
    change = {**change, "total_requests": None}

# --- 2.2 Status summary ----------------------------------------------------
st.caption(
    f"**Data Source:** `{summary.get('source', 'unknown')}`  ·  "
    f"**Last Updated:** {summary.get('last_updated', 'unknown')}  ·  "
    f"**Window:** last {DEFAULT_WINDOW_DAYS}d at {series.get('interval', DEFAULT_INTERVAL)}"
)
if str(summary.get("source", "")).endswith("synthetic_backfill"):
    st.warning(
        "This window contains backfilled entries that no client actually sent. "
        "They are here to demonstrate the charts; they are not real traffic."
    )

# --- 2.3 KPI metrics -------------------------------------------------------
one, two, three, four = st.columns(4)
show_metric(one, "Total Requests", current.get("total_requests"),
            change.get("total_requests"), "{:,.0f}", "{:+,.0f}")
show_metric(two, "Avg Response Time", current.get("avg_response_time_ms"),
            change.get("avg_response_time_ms"), "{:.1f}ms", "{:+.1f}ms", inverse=True)
# `pp` rather than `%`: the change in a percentage is percentage points, and
# calling it a percentage is the classic way to make a jump from 1% to 2% read
# as "+1%" when it doubled.
show_metric(three, "Avg Error Rate", current.get("error_rate"),
            change.get("error_rate"), "{:.2f}%", "{:+.2f}pp", scale=100.0, inverse=True)
show_metric(four, "Avg Probability", current.get("avg_probability"),
            change.get("avg_probability"), "{:.3f}", "{:+.3f}")

# --- 2.6 Alerts ------------------------------------------------------------
error_rate = current.get("error_rate")
response_time = current.get("avg_response_time_ms")
probability_drift = change.get("avg_probability")

if error_rate is not None and error_rate > ERROR_RATE_ALERT:
    st.warning(
        f"⚠️ Error rate is high: {error_rate * 100:.2f}% of requests in this window did not "
        f"return 2xx, above the {ERROR_RATE_ALERT * 100:.0f}% threshold."
    )
if response_time is not None and response_time > RESPONSE_TIME_ALERT_MS:
    st.warning(
        f"⚠️ Average latency is high: {response_time:.1f} ms, above the "
        f"{RESPONSE_TIME_ALERT_MS:.0f} ms threshold."
    )
if probability_drift is not None and abs(probability_drift) >= PROBABILITY_DRIFT_ALERT:
    st.warning(
        f"⚠️ Average predicted probability moved by {probability_drift:+.3f} against the "
        "previous window. Check whether the input mix or the model changed."
    )

# --- 3.6.1 Empty state -----------------------------------------------------
rows = series.get("data") or []
if not rows:
    st.info(
        "No data to display in the current time window.\n\n"
        "The log is in memory and starts empty on every restart — call "
        "`/predict`, or run `python scripts/seed_traffic.py`, then reload."
    )
    st.stop()

frame = pd.DataFrame(rows)
if "timestamp" in frame.columns:
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame = frame.sort_values("timestamp").reset_index(drop=True)
frame["error_rate_pct"] = pd.to_numeric(frame.get("error_rate"), errors="coerce") * 100

# --- 2.4 Trend charts ------------------------------------------------------
line_chart(frame, "requests", "Requests per Interval", "requests")
line_chart(frame, "avg_response_time_ms", "Average Response Time (ms)", "ms")
line_chart(frame, "error_rate_pct", "Error Rate (%)", "%")
# The probability axis is pinned to its full range. Autoscaling it turns a
# half-point wobble into a mountain range, which is the opposite of what a
# drift chart is for.
line_chart(frame, "avg_probability", "Average Predicted Probability", "probability", (0.0, 1.0))

# --- 2.5 Raw data ----------------------------------------------------------
with st.expander("Raw Data"):
    st.dataframe(
        frame.drop(columns=["error_rate_pct"]),
        width="stretch",
        hide_index=False,
        column_config={
            "timestamp": st.column_config.DatetimeColumn("timestamp"),
            "requests": st.column_config.NumberColumn("requests", format="%d"),
            "avg_response_time_ms": st.column_config.NumberColumn(
                "avg_response_time_ms", format="%.4f"),
            "error_rate": st.column_config.NumberColumn("error_rate", format="%.4f"),
            "avg_probability": st.column_config.NumberColumn("avg_probability", format="%.4f"),
        },
    )
    st.caption(
        f"{len(frame)} buckets · {int(frame['requests'].sum()):,} requests · "
        "the same rows the charts above are drawn from."
    )
