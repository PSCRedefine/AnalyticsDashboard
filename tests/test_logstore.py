"""The buffer, its filters, and the promise that it cannot break a request."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from analytics_dashboard.logstore import (
    MIXED_SOURCE,
    REAL_SOURCE,
    RequestLogStore,
    is_error,
    resolve_window,
    status_family,
)

from .conftest import NOW, entry


# --- classification --------------------------------------------------------

@pytest.mark.parametrize("code,family", [
    (200, "2xx"), (204, "2xx"), (301, "3xx"), (404, "4xx"), (422, "4xx"),
    (500, "5xx"), (503, "5xx"), (99, "other"), (600, "other"),
])
def test_status_family(code, family):
    assert status_family(code) == family


@pytest.mark.parametrize("code,error", [
    (200, False), (299, False), (300, True), (404, True), (500, True),
])
def test_anything_that_is_not_a_2xx_counts_as_an_error(code, error):
    """Specification 4.5 step 10. A 404 is the caller's fault and still unhealthy."""
    assert is_error(code) is error


# --- the buffer ------------------------------------------------------------

def test_records_the_four_required_fields(store):
    store.record(endpoint="/predict", status_code=200, response_time_ms=12.5)
    recorded = store.snapshot()[0]
    assert set(recorded) >= {"timestamp", "endpoint", "status_code", "response_time_ms"}
    assert recorded["response_time_ms"] == 12.5


def test_prediction_fields_are_optional(store):
    store.record(endpoint="/health", status_code=200, response_time_ms=1.0)
    assert "probability" not in store.snapshot()[0]


def test_prediction_fields_are_kept_when_supplied(store):
    store.record(endpoint="/predict", status_code=200, response_time_ms=1.0,
                 probability=0.42, model_version="1.0.0")
    recorded = store.snapshot()[0]
    assert recorded["probability"] == 0.42
    assert recorded["model_version"] == "1.0.0"


def test_a_malformed_entry_is_dropped_rather_than_raised(store):
    """Observing must never break serving. This is the whole contract."""
    store.record(endpoint="/predict", status_code="not-a-number", response_time_ms=1.0)
    assert len(store) == 0


def test_the_buffer_is_bounded_and_drops_the_oldest():
    small = RequestLogStore(capacity=3)
    for index in range(5):
        small.record(endpoint=f"/{index}", status_code=200, response_time_ms=1.0)
    assert [e["endpoint"] for e in small.snapshot()] == ["/2", "/3", "/4"]


def test_naive_timestamps_are_normalised_to_utc(store):
    store.record(endpoint="/predict", status_code=200, response_time_ms=1.0,
                 timestamp=datetime(2026, 4, 28, 12, 0))
    assert store.snapshot()[0]["timestamp"].tzinfo is not None


# --- selection -------------------------------------------------------------

def test_selection_is_half_open_so_windows_tile_without_overlap(store):
    """The boundary entry belongs to exactly one of two consecutive windows."""
    store.extend([entry(minutes_ago=0)])
    assert len(store.select(NOW - timedelta(hours=1), NOW)) == 0
    assert len(store.select(NOW, NOW + timedelta(hours=1))) == 1


def test_selection_filters_by_endpoint(store):
    store.extend([entry(endpoint="/predict"), entry(endpoint="/predict/batch")])
    window = (NOW - timedelta(hours=1), NOW + timedelta(hours=1))
    assert len(store.select(*window, endpoint="/predict")) == 1


def test_selection_filters_by_model_version(store):
    store.extend([entry(model_version="1.0.0"), entry(model_version="2.0.0")])
    window = (NOW - timedelta(hours=1), NOW + timedelta(hours=1))
    assert len(store.select(*window, model_version="2.0.0")) == 1


def test_selection_filters_by_status_family(store):
    store.extend([entry(status_code=200), entry(status_code=404), entry(status_code=500)])
    window = (NOW - timedelta(hours=1), NOW + timedelta(hours=1))
    assert len(store.select(*window, status_code_family="4xx")) == 1
    assert len(store.select(*window, status_code_family="5xx")) == 1


def test_filters_combine(store):
    store.extend([
        entry(endpoint="/predict", status_code=200),
        entry(endpoint="/predict", status_code=500),
        entry(endpoint="/health", status_code=500),
    ])
    window = (NOW - timedelta(hours=1), NOW + timedelta(hours=1))
    selected = store.select(*window, endpoint="/predict", status_code_family="5xx")
    assert len(selected) == 1


# --- honesty about the source ---------------------------------------------

def test_real_entries_report_the_real_source(store):
    store.extend([entry()])
    assert store.source() == REAL_SOURCE


def test_one_synthetic_entry_changes_the_source(store):
    """The Data Source field only means something if it can say `not real`."""
    store.extend([entry()])
    store.record(endpoint="/predict", status_code=200, response_time_ms=1.0, synthetic=True)
    assert store.source() == MIXED_SOURCE


def test_the_source_is_reported_per_window_not_globally(store):
    store.record(endpoint="/predict", status_code=200, response_time_ms=1.0,
                 timestamp=NOW - timedelta(days=30), synthetic=True)
    recent = [entry()]
    store.extend(recent)
    assert store.source(store.select(NOW - timedelta(hours=1), NOW + timedelta(hours=1))) \
        == REAL_SOURCE


# --- window defaults -------------------------------------------------------

def test_the_window_defaults_to_the_last_seven_days():
    start, end = resolve_window(None, None, 7)
    assert (end - start).days == 7
    assert abs((datetime.now(UTC) - end).total_seconds()) < 5


def test_an_explicit_start_is_respected():
    start, end = resolve_window(NOW - timedelta(days=1), NOW, 7)
    assert (start, end) == (NOW - timedelta(days=1), NOW)


def test_last_updated_is_the_newest_entry(store):
    store.extend([entry(minutes_ago=60), entry(minutes_ago=5)])
    assert store.last_updated() == NOW - timedelta(minutes=5)


def test_last_updated_of_an_empty_store_is_now(store):
    assert abs((datetime.now(UTC) - store.last_updated()).total_seconds()) < 5
