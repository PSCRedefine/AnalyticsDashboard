"""The arithmetic behind the KPI cards and the four charts.

The recurring subject here is nothing: an empty window, an empty bucket, a
missing previous period. Getting those wrong does not raise, it draws a
confident line at zero, which is worse.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from analytics_dashboard.aggregate import delta, parse_interval, summarise, timeseries

from .conftest import NOW, entry


# --- interval parsing ------------------------------------------------------

@pytest.mark.parametrize("text,alias,seconds", [
    ("5min", "5min", 300),
    ("1h", "1h", 3600),
    ("1d", "1d", 86400),
    ("30s", "30s", 30),
    ("15 minutes", "15min", 900),
    (" 2H ", "2h", 7200),
])
def test_valid_intervals(text, alias, seconds):
    parsed, duration = parse_interval(text)
    assert parsed == alias
    assert duration == timedelta(seconds=seconds)


def test_a_bare_m_means_minutes_not_months():
    """Pandas reads `m` as month-end. `5m` becoming five months would be silent."""
    assert parse_interval("5m") == ("5min", timedelta(minutes=5))


@pytest.mark.parametrize("text", ["", None, "hour", "1x", "-1h", "0h", "1", "1 fortnight", "5s"])
def test_invalid_intervals_raise(text):
    with pytest.raises(ValueError):
        parse_interval(text)


# --- summarise -------------------------------------------------------------

def test_an_empty_window_counts_zero_and_averages_nothing():
    """Zero requests is a count. It is not an average response time of 0 ms."""
    assert summarise([]) == {
        "total_requests": 0,
        "avg_response_time_ms": None,
        "error_rate": None,
        "avg_probability": None,
    }


def test_the_four_aggregates():
    rows = [
        entry(response_time_ms=10.0, probability=0.2),
        entry(response_time_ms=20.0, probability=0.4),
        entry(response_time_ms=30.0, status_code=500, probability=None),
    ]
    result = summarise(rows)
    assert result["total_requests"] == 3
    assert result["avg_response_time_ms"] == 20.0
    assert result["error_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert result["avg_probability"] == pytest.approx(0.3)


def test_probability_averages_only_over_rows_that_have_one():
    """A failed request never reached the model, so it must not count as a 0."""
    rows = [entry(probability=0.8), entry(status_code=500, probability=None)]
    assert summarise(rows)["avg_probability"] == pytest.approx(0.8)


def test_a_window_with_no_probabilities_at_all_reports_none():
    assert summarise([entry(endpoint="/health", probability=None)])["avg_probability"] is None


# --- delta -----------------------------------------------------------------

def test_delta_is_current_minus_previous():
    current = summarise([entry(response_time_ms=30.0, probability=0.4)])
    previous = summarise([entry(response_time_ms=10.0, probability=0.1)])
    result = delta(current, previous)
    assert result["total_requests"] == 0
    assert result["avg_response_time_ms"] == pytest.approx(20.0)
    assert result["avg_probability"] == pytest.approx(0.3)


def test_delta_against_an_empty_previous_window_is_null_not_the_current_value():
    """Specification 3.6.3. No comparison and no change are different statements."""
    current = summarise([entry(response_time_ms=30.0, probability=0.4)])
    result = delta(current, summarise([]))
    assert result["avg_response_time_ms"] is None
    assert result["error_rate"] is None
    assert result["avg_probability"] is None
    assert result["total_requests"] == 1


def test_the_request_delta_can_be_negative():
    current = summarise([entry()])
    previous = summarise([entry(), entry(), entry()])
    assert delta(current, previous)["total_requests"] == -2


# --- timeseries ------------------------------------------------------------

def test_an_empty_window_produces_no_rows():
    assert timeseries([], "1h") == []


def test_one_row_per_bucket_with_the_four_chart_fields():
    # Both entries land on 12:00, so they share a bucket.
    rows = timeseries([entry(minutes_ago=0), entry(minutes_ago=0)], "1h")
    assert len(rows) == 1
    assert set(rows[0]) == {
        "timestamp", "requests", "avg_response_time_ms", "error_rate", "avg_probability",
    }
    assert rows[0]["requests"] == 2


def test_buckets_are_returned_oldest_first():
    rows = timeseries([entry(minutes_ago=0), entry(minutes_ago=180)], "1h")
    assert [row["timestamp"] for row in rows] == sorted(row["timestamp"] for row in rows)


def test_an_empty_bucket_keeps_its_place_with_zero_requests():
    """Dropping it would join the line across an outage and hide it."""
    rows = timeseries([entry(minutes_ago=0), entry(minutes_ago=180)], "1h")
    assert len(rows) == 4
    assert [row["requests"] for row in rows] == [1, 0, 0, 1]


def test_an_empty_bucket_has_no_averages_rather_than_zeroes():
    rows = timeseries([entry(minutes_ago=0), entry(minutes_ago=180)], "1h")
    quiet = [row for row in rows if row["requests"] == 0]
    assert quiet
    for row in quiet:
        assert row["avg_response_time_ms"] is None
        assert row["error_rate"] is None
        assert row["avg_probability"] is None


def test_error_rate_is_a_fraction_not_a_percentage():
    """The page multiplies by 100. Doing it here as well would give 10,000%."""
    rows = timeseries([entry(status_code=500), entry(status_code=200)], "1h")
    assert rows[0]["error_rate"] == pytest.approx(0.5)


def test_a_bucket_of_only_failures_has_no_probability():
    rows = timeseries([entry(status_code=500, probability=None)], "1h")
    assert rows[0]["avg_probability"] is None
    assert rows[0]["error_rate"] == 1.0


def test_entries_without_a_probability_column_at_all_do_not_break_the_frame():
    rows = timeseries([{"timestamp": NOW, "endpoint": "/health",
                        "status_code": 200, "response_time_ms": 1.0}], "1h")
    assert rows[0]["avg_probability"] is None


def test_a_finer_interval_produces_more_buckets():
    rows = timeseries([entry(minutes_ago=0), entry(minutes_ago=30)], "5min")
    assert len(rows) == 7


def test_an_interval_that_would_explode_the_response_is_refused():
    rows = [entry(minutes_ago=0), entry(minutes_ago=60 * 24 * 30)]
    with pytest.raises(ValueError, match="buckets"):
        timeseries(rows, "30s")
