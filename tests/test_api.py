"""The two analytics routes, and the middleware that feeds them.

The middleware tests go through the real service on purpose. A middleware is a
claim about what happens around a request, and the only way to check that claim
is to make a request.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from analytics_dashboard.logstore import REAL_SOURCE

from .conftest import VALID_USER, VALID_VIDEO, entry

NOW = datetime.now(UTC)


def payload(user_id=VALID_USER, video_id=VALID_VIDEO, watch_time=45.0):
    return {"user_id": user_id, "video_id": video_id, "watch_time": watch_time}


def seed(client, rows):
    client.app.state.store.extend(rows)


def recent(minutes_ago=1, **kwargs):
    return entry(minutes_ago=minutes_ago, now=NOW, **kwargs)


# --- 4.2 The middleware ----------------------------------------------------

def test_a_prediction_is_logged_with_all_six_fields(client):
    assert client.post("/predict", json=payload()).status_code == 200
    recorded = client.app.state.store.snapshot()[-1]
    assert recorded["endpoint"] == "/predict"
    assert recorded["status_code"] == 200
    assert recorded["response_time_ms"] > 0
    assert 0.0 <= recorded["probability"] <= 1.0
    assert recorded["model_version"] == "1.0.0"


def test_the_probability_comes_from_request_state(client):
    """Specification 4.3. The transport layer cannot know this; the route hands it over."""
    body = client.post("/predict", json=payload()).json()
    assert client.app.state.store.snapshot()[-1]["probability"] == pytest.approx(
        body["probability"], abs=1e-6
    )


def test_a_failed_prediction_is_logged_with_its_status_and_no_probability(client):
    """The error-rate chart exists for exactly these rows."""
    assert client.post("/predict", json=payload(user_id="user_999999999")).status_code == 404
    recorded = client.app.state.store.snapshot()[-1]
    assert recorded["status_code"] == 404
    assert "probability" not in recorded


def test_a_schema_rejection_is_logged_too(client):
    client.post("/predict", json={"user_id": "nope", "video_id": "x", "watch_time": -1})
    assert client.app.state.store.snapshot()[-1]["status_code"] == 422


@pytest.mark.parametrize("path", ["/", "/docs", "/openapi.json", "/health"])
def test_internal_routes_are_not_logged(client, path):
    client.get(path)
    assert len(client.app.state.store) == 0


def test_the_analytics_routes_do_not_log_themselves(client):
    """Otherwise every dashboard refresh inflates the count it is about to render."""
    client.get("/analytics/summary")
    client.get("/analytics/timeseries")
    assert len(client.app.state.store) == 0


# --- 4.4 /analytics/summary ------------------------------------------------

def test_summary_returns_every_field_the_page_reads(client):
    body = client.get("/analytics/summary").json()
    assert set(body) >= {
        "source", "last_updated", "start", "end", "filters",
        "current", "previous", "delta",
    }


def test_summary_defaults_to_a_seven_day_window(client):
    body = client.get("/analytics/summary").json()
    start = datetime.fromisoformat(body["start"])
    end = datetime.fromisoformat(body["end"])
    assert (end - start).days == 7


def test_summary_compares_against_the_window_immediately_before(client):
    """Specification 4.4 step 6: previous is `[start − window, start)`."""
    seed(client, [
        recent(minutes_ago=60, response_time_ms=30.0),
        recent(minutes_ago=60 * 25, response_time_ms=10.0),
    ])
    body = client.get("/analytics/summary", params={
        "start": (NOW - timedelta(days=1)).isoformat(),
        "end": NOW.isoformat(),
    }).json()
    assert body["current"]["total_requests"] == 1
    assert body["previous"]["total_requests"] == 1
    assert body["delta"]["avg_response_time_ms"] == pytest.approx(20.0)


def test_summary_of_an_empty_window_is_zeroes_and_nulls(client):
    body = client.get("/analytics/summary").json()
    assert body["current"]["total_requests"] == 0
    assert body["current"]["avg_response_time_ms"] is None
    assert body["current"]["avg_probability"] is None


def test_summary_reports_the_source(client):
    seed(client, [recent()])
    assert client.get("/analytics/summary").json()["source"] == REAL_SOURCE


def test_summary_echoes_its_filters(client):
    body = client.get("/analytics/summary", params={
        "endpoint": "/predict", "status_code_family": "2xx",
    }).json()
    assert body["filters"]["endpoint"] == "/predict"
    assert body["filters"]["status_code_family"] == "2xx"
    assert body["filters"]["model_version"] is None


def test_summary_filters_narrow_the_result(client):
    seed(client, [
        recent(endpoint="/predict", status_code=200),
        recent(endpoint="/predict", status_code=500),
        recent(endpoint="/health", status_code=200),
    ])
    body = client.get("/analytics/summary", params={"status_code_family": "5xx"}).json()
    assert body["current"]["total_requests"] == 1
    assert body["current"]["error_rate"] == 1.0


# --- 4.5 /analytics/timeseries ---------------------------------------------

def test_timeseries_returns_every_field_the_charts_read(client):
    body = client.get("/analytics/timeseries").json()
    assert set(body) >= {"source", "last_updated", "start", "end", "interval", "data"}


def test_timeseries_points_carry_the_five_chart_fields(client):
    seed(client, [recent()])
    point = client.get("/analytics/timeseries").json()["data"][0]
    assert set(point) == {
        "timestamp", "requests", "avg_response_time_ms", "error_rate", "avg_probability",
    }


def test_timeseries_defaults_to_one_hour_buckets(client):
    assert client.get("/analytics/timeseries").json()["interval"] == "1h"


def test_timeseries_honours_the_interval(client):
    """19 minutes apart: one bucket at 1h, four or five at 5min.

    The exact count depends on where the clock sits relative to a five-minute
    boundary, so the assertion is about the relationship rather than a number
    that would make this test fail on the hour.
    """
    seed(client, [recent(minutes_ago=1), recent(minutes_ago=20)])
    hourly = client.get("/analytics/timeseries", params={"interval": "1h"}).json()
    fine = client.get("/analytics/timeseries", params={"interval": "5min"}).json()
    assert fine["interval"] == "5min"
    assert len(fine["data"]) > len(hourly["data"])
    assert sum(p["requests"] for p in fine["data"]) == 2
    assert sum(p["requests"] for p in hourly["data"]) == 2


def test_an_empty_window_returns_an_empty_data_array_not_an_error(client):
    """Specification 4.5 step 7. The page renders the empty state from this."""
    body = client.get("/analytics/timeseries")
    assert body.status_code == 200
    assert body.json()["data"] == []


# --- validation ------------------------------------------------------------

def test_an_inverted_window_is_a_400(client):
    """A swapped pair of dates must not read as `no traffic`."""
    for route in ("/analytics/summary", "/analytics/timeseries"):
        response = client.get(route, params={
            "start": NOW.isoformat(), "end": (NOW - timedelta(days=1)).isoformat(),
        })
        assert response.status_code == 400


def test_an_equal_start_and_end_is_a_400(client):
    response = client.get("/analytics/summary", params={
        "start": NOW.isoformat(), "end": NOW.isoformat(),
    })
    assert response.status_code == 400


@pytest.mark.parametrize("interval", ["hour", "1x", "0h", "", "1 fortnight"])
def test_an_invalid_interval_is_a_400(client, interval):
    assert client.get("/analytics/timeseries",
                      params={"interval": interval}).status_code == 400


def test_an_unparseable_timestamp_is_a_400(client):
    assert client.get("/analytics/summary",
                      params={"start": "last tuesday"}).status_code == 400


def test_an_unknown_status_family_is_a_400(client):
    assert client.get("/analytics/summary",
                      params={"status_code_family": "6xx"}).status_code == 400


def test_a_naive_timestamp_is_read_as_utc(client):
    """Guessing a local zone would make the same query mean different things per host."""
    body = client.get("/analytics/summary", params={
        "start": "2026-04-21T10:30:00", "end": "2026-04-28T10:30:00",
    }).json()
    assert body["start"] == "2026-04-21T10:30:00+00:00"


def test_a_z_suffix_is_accepted(client):
    body = client.get("/analytics/summary", params={
        "start": "2026-04-21T10:30:00Z", "end": "2026-04-28T10:30:00Z",
    }).json()
    assert body["end"] == "2026-04-28T10:30:00+00:00"


# --- the backfill route ----------------------------------------------------

def test_backfill_is_disabled_by_default(client):
    """It writes entries nobody served, so it is off unless explicitly enabled."""
    assert client.post("/analytics/backfill", json=[]).status_code == 404


# --- the cards and the charts agree ---------------------------------------

def test_the_summary_total_matches_the_sum_of_the_buckets(client):
    """A page whose KPI card disagrees with its own chart is worse than no page."""
    seed(client, [recent(minutes_ago=m) for m in (1, 5, 70, 200, 4000)])
    total = client.get("/analytics/summary").json()["current"]["total_requests"]
    buckets = client.get("/analytics/timeseries").json()["data"]
    assert total == sum(point["requests"] for point in buckets)


def test_backfill_writes_flagged_entries_when_enabled(client, monkeypatch):
    """Everything it writes changes what `source` reports, on every route."""
    monkeypatch.setenv("ANALYTICS_ALLOW_BACKFILL", "1")
    response = client.post("/analytics/backfill", json=[{
        "timestamp": (NOW - timedelta(hours=2)).isoformat(),
        "endpoint": "/predict",
        "status_code": 200,
        "response_time_ms": 12.0,
        "probability": 0.3,
    }])
    assert response.status_code == 200
    assert response.json()["written"] == 1
    body = client.get("/analytics/summary").json()
    assert body["source"] == "in_memory_api_logs+synthetic_backfill"
    assert body["current"]["total_requests"] == 1


def test_a_route_that_raises_is_logged_as_a_500(client):
    """The error-rate chart must not go quiet when the service starts failing."""
    @client.app.get("/boom")
    def boom():
        raise RuntimeError("deliberate")

    with pytest.raises(RuntimeError):
        client.get("/boom")
    recorded = client.app.state.store.snapshot()[-1]
    assert recorded["endpoint"] == "/boom"
    assert recorded["status_code"] == 500
