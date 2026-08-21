"""Shared fixtures.

Analytics tests need control over time, which real traffic does not give you: a
seven-day window cannot be exercised by making requests, because every request
you make lands in the same minute. So most tests build a store directly and put
entries where they need them.

`client` is the exception. It exists to prove the middleware actually records
what it claims to, and it does that by making real calls against the real model.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from analytics_dashboard.api import create_app
from analytics_dashboard.config import DATA_DIR, METADATA_PATH, MODEL_PATH
from analytics_dashboard.logstore import RequestLogStore

VALID_USER = "user_000001"
VALID_VIDEO = "video_0000001"

# A fixed instant, so a window computed from it is the same window on every run.
NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


@pytest.fixture
def store() -> RequestLogStore:
    return RequestLogStore(capacity=1000)


@pytest.fixture
def client() -> TestClient:
    """The real service, with a fresh log per test."""
    app = create_app(
        model_path=MODEL_PATH,
        metadata_path=METADATA_PATH,
        users_path=DATA_DIR / "users.csv",
        videos_path=DATA_DIR / "videos.csv",
        store=RequestLogStore(capacity=5000),
    )
    return TestClient(app)


def entry(
    minutes_ago: float = 0,
    endpoint: str = "/predict",
    status_code: int = 200,
    response_time_ms: float = 20.0,
    probability: float | None = 0.3,
    model_version: str | None = "1.0.0",
    now: datetime = NOW,
) -> dict:
    """One log record, positioned relative to a fixed `now`."""
    return {
        "endpoint": endpoint,
        "status_code": status_code,
        "response_time_ms": response_time_ms,
        "timestamp": now - timedelta(minutes=minutes_ago),
        "probability": probability,
        "model_version": model_version,
    }
