"""FastAPI service with request analytics.

Two ideas, in order of importance.

**The log comes first.** The Analytics page has no data source of its own: every
number on it is derived from requests this process has served. So the middleware
in ``middleware.py`` is not a supporting detail, it is the feature — the routes
below are a query language over what it recorded.

**The window arithmetic is shared.** ``/analytics/summary`` and
``/analytics/timeseries`` resolve their window, validate it and apply their
filters through the same code, because a page that draws its KPI cards from one
window and its charts from a slightly different one is a page that quietly
contradicts itself.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import __version__
from .aggregate import delta, isoformat, parse_interval, summarise, timeseries
from .config import (
    DEFAULT_INTERVAL,
    DEFAULT_WINDOW_DAYS,
    LOG_CAPACITY,
    METADATA_PATH,
    MODEL_PATH,
    USERS_PATH,
    VIDEOS_PATH,
)
from .features import MAX_WATCH_TIME_SECONDS, FeatureStore
from .logstore import STATUS_FAMILIES, RequestLogStore, resolve_window
from .middleware import RequestLoggingMiddleware

logger = logging.getLogger("analytics_dashboard.api")

def backfill_enabled() -> bool:
    """Whether the demonstration backfill route will accept writes.

    Read per request rather than captured at import, so the switch is a property
    of how the process was started rather than of when this module happened to
    be imported — and so a test can flip it without reloading the module.
    """
    return os.getenv("ANALYTICS_ALLOW_BACKFILL", "").strip().lower() in {"1", "true", "yes"}


def parse_moment(value: str | None, field: str) -> datetime | None:
    """Parse an ISO 8601 timestamp, treating a naive one as UTC.

    A caller who writes `2026-04-21T10:30:00` means a wall clock, and the only
    wall clock this service has is UTC. Guessing a local zone would make the
    same query return different windows on different machines.
    """
    if value is None or not str(value).strip():
        return None
    try:
        moment = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"{field} is not an ISO 8601 timestamp: {value!r}"
        ) from exc
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


class WindowQuery:
    """The parameters both analytics routes share, resolved and validated once."""

    def __init__(
        self,
        start: str | None = Query(default=None, description="ISO 8601; defaults to end − 7 days"),
        end: str | None = Query(default=None, description="ISO 8601; defaults to now (UTC)"),
        endpoint: str | None = Query(default=None, description="exact path, e.g. /predict"),
        model_version: str | None = Query(default=None),
        status_code_family: str | None = Query(default=None, description="2xx, 3xx, 4xx or 5xx"),
    ) -> None:
        self.start, self.end = resolve_window(
            parse_moment(start, "start"), parse_moment(end, "end"), DEFAULT_WINDOW_DAYS
        )
        # Specification 4.4 step 4 / 4.5 step 4. An inverted window is a caller
        # bug, not an empty result — returning `[]` for it would let a swapped
        # pair of dates read as "no traffic".
        if self.end <= self.start:
            raise HTTPException(status_code=400, detail="end must be later than start")
        if status_code_family and status_code_family not in STATUS_FAMILIES:
            raise HTTPException(
                status_code=400,
                detail=f"status_code_family must be one of {', '.join(STATUS_FAMILIES)}",
            )
        self.endpoint = endpoint or None
        self.model_version = model_version or None
        self.status_code_family = status_code_family or None

    @property
    def filters(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "model_version": self.model_version,
            "status_code_family": self.status_code_family,
        }

    @property
    def previous(self) -> tuple[datetime, datetime]:
        """Specification 4.4 step 6: the window of equal length ending where this one starts."""
        return self.start - (self.end - self.start), self.start


class Aggregate(BaseModel):
    total_requests: int = 0
    avg_response_time_ms: float | None = None
    error_rate: float | None = None
    avg_probability: float | None = None


class SummaryResponse(BaseModel):
    source: str
    last_updated: str
    start: str
    end: str
    filters: dict[str, Any]
    current: Aggregate
    previous: Aggregate
    delta: Aggregate


class TimeseriesPoint(BaseModel):
    timestamp: str
    requests: int
    avg_response_time_ms: float | None = None
    error_rate: float | None = None
    avg_probability: float | None = None


class TimeseriesResponse(BaseModel):
    source: str
    last_updated: str
    start: str
    end: str
    interval: str
    data: list[TimeseriesPoint] = Field(default_factory=list)


class PredictionRequest(BaseModel):
    user_id: str = Field(min_length=6, max_length=80, examples=["user_000001"])
    video_id: str = Field(min_length=7, max_length=80, examples=["video_0000001"])
    watch_time: float = Field(ge=0, le=MAX_WATCH_TIME_SECONDS, examples=[45.0])
    hour_of_day: int | None = Field(default=None, ge=0, le=23, examples=[14])

    @field_validator("user_id", "video_id")
    @classmethod
    def validate_identifier(cls, value: str, info) -> str:
        prefix = "user_" if info.field_name == "user_id" else "video_"
        if not str(value).startswith(prefix):
            raise ValueError(f"{info.field_name} must start with '{prefix}'")
        return str(value)


class PredictionResponse(BaseModel):
    user_id: str
    video_id: str
    watch_time: float
    hour_of_day: int
    probability: float
    predicted_engaged: bool
    threshold: float
    model_version: str
    response_time_ms: float
    timestamp: str

    model_config = {"protected_namespaces": ()}


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    store_loaded: bool
    logged_requests: int
    log_capacity: int
    uptime_seconds: float
    model_name: str
    version: str
    timestamp: str

    model_config = {"protected_namespaces": ()}


def predict_probabilities(model: Any, frame: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        raw = np.asarray(model.predict_proba(frame))[:, 1]
    else:
        raw = np.asarray(model.predict(frame)).ravel()
    return np.clip(raw.astype(float), 0.0, 1.0)


def create_app(
    model_path: Path = MODEL_PATH,
    metadata_path: Path = METADATA_PATH,
    users_path: Path = USERS_PATH,
    videos_path: Path = VIDEOS_PATH,
    store: RequestLogStore | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Cognitive Shorts — Analytics API",
        version=__version__,
        description="Prediction service with in-memory request analytics.",
    )

    app.state.store = store or RequestLogStore()
    app.state.started_at = time.time()
    app.state.model = None
    app.state.metadata = {}
    app.state.features = None

    app.add_middleware(RequestLoggingMiddleware, store=app.state.store)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    try:
        app.state.model = joblib.load(model_path)
    except Exception as exc:  # noqa: BLE001 - the analytics routes do not need a model
        logger.error("could not load the model: %s", exc)
    try:
        if Path(metadata_path).exists():
            app.state.metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read the metadata file: %s", exc)
    try:
        app.state.features = FeatureStore.from_csv(str(users_path), str(videos_path))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not load the lookup tables: %s", exc)

    def model_version() -> str:
        return str(app.state.metadata.get("model_version", __version__))

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="healthy" if app.state.model is not None else "degraded",
            model_loaded=app.state.model is not None,
            store_loaded=app.state.features is not None,
            logged_requests=len(app.state.store),
            log_capacity=app.state.store.capacity,
            uptime_seconds=round(time.time() - app.state.started_at, 1),
            model_name=str(app.state.metadata.get("model_name", "unknown")),
            version=__version__,
            timestamp=datetime.now(UTC).isoformat(),
        )

    @app.post("/predict", response_model=PredictionResponse)
    def predict(payload: PredictionRequest, request: Request) -> PredictionResponse:
        """Score one interaction and hand the middleware what it cannot see.

        Specification 4.3: the probability and the model version are business
        facts the transport layer has no way to know, so the route writes them
        onto ``request.state`` and the middleware reads them back once the
        response exists. Without this the Avg Probability card has no source.
        """
        if app.state.model is None or app.state.features is None:
            raise HTTPException(status_code=503, detail="model or lookup tables are not loaded")
        started = time.perf_counter()
        now = datetime.now(UTC)
        hour = payload.hour_of_day if payload.hour_of_day is not None else now.hour
        try:
            frame = app.state.features.build_one(
                payload.user_id, payload.video_id, payload.watch_time,
                pd.Timestamp(now).replace(hour=hour),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        probability = float(predict_probabilities(app.state.model, frame)[0])
        cut = float(app.state.metadata.get("recommended_threshold", 0.5))

        request.state.probability = probability
        request.state.model_version = model_version()

        return PredictionResponse(
            user_id=payload.user_id,
            video_id=payload.video_id,
            watch_time=payload.watch_time,
            hour_of_day=hour,
            probability=round(probability, 6),
            predicted_engaged=probability >= cut,
            threshold=cut,
            model_version=model_version(),
            response_time_ms=round((time.perf_counter() - started) * 1000, 3),
            timestamp=datetime.now(UTC).isoformat(),
        )

    @app.get("/analytics/summary", response_model=SummaryResponse)
    def analytics_summary(window: WindowQuery = Depends()) -> SummaryResponse:
        """Specification 4.4 — this window, the one before it, and the difference."""
        store: RequestLogStore = app.state.store
        current_rows = store.select(window.start, window.end, **window.filters)
        previous_start, previous_end = window.previous
        previous_rows = store.select(previous_start, previous_end, **window.filters)

        current = summarise(current_rows)
        previous = summarise(previous_rows)
        logger.info(
            "/analytics/summary %s → %s: %d current, %d previous",
            isoformat(window.start), isoformat(window.end),
            current["total_requests"], previous["total_requests"],
        )
        return SummaryResponse(
            source=store.source(current_rows + previous_rows),
            last_updated=isoformat(store.last_updated()),
            start=isoformat(window.start),
            end=isoformat(window.end),
            filters=window.filters,
            current=Aggregate(**current),
            previous=Aggregate(**previous),
            delta=Aggregate(**delta(current, previous)),
        )

    @app.get("/analytics/timeseries", response_model=TimeseriesResponse)
    def analytics_timeseries(
        window: WindowQuery = Depends(),
        interval: str = Query(default=DEFAULT_INTERVAL, description="5min, 1h, 1d …"),
    ) -> TimeseriesResponse:
        """Specification 4.5 — one row per time bucket, oldest first."""
        try:
            alias, _ = parse_interval(interval)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        store: RequestLogStore = app.state.store
        rows = store.select(window.start, window.end, **window.filters)
        try:
            data = timeseries(rows, alias)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        logger.info(
            "/analytics/timeseries %s → %s at %s: %d buckets from %d requests",
            isoformat(window.start), isoformat(window.end), alias, len(data), len(rows),
        )
        return TimeseriesResponse(
            source=store.source(rows),
            last_updated=isoformat(store.last_updated()),
            start=isoformat(window.start),
            end=isoformat(window.end),
            interval=alias,
            data=[TimeseriesPoint(**row) for row in data],
        )

    @app.post("/analytics/backfill", include_in_schema=False)
    def analytics_backfill(entries: list[dict[str, Any]] = Body(...)) -> dict[str, Any]:
        """Inject historical entries so the charts have a week to draw. Development only.

        Disabled unless ``ANALYTICS_ALLOW_BACKFILL`` is set, and everything it
        writes is flagged ``synthetic``, which changes what ``source`` reports on
        every route. The page then says
        ``in_memory_api_logs+synthetic_backfill`` instead of
        ``in_memory_api_logs``, so a reader is never shown fabricated traffic
        that claims to be real.
        """
        if not backfill_enabled():
            raise HTTPException(
                status_code=404,
                detail="backfill is disabled; set ANALYTICS_ALLOW_BACKFILL=1 to enable it",
            )
        store: RequestLogStore = app.state.store
        prepared = []
        for entry in entries:
            prepared.append({
                "endpoint": entry.get("endpoint", "/predict"),
                "status_code": int(entry.get("status_code", 200)),
                "response_time_ms": float(entry.get("response_time_ms", 0.0)),
                "timestamp": parse_moment(entry.get("timestamp"), "timestamp"),
                "probability": entry.get("probability"),
                "model_version": entry.get("model_version"),
                "synthetic": True,
            })
        written = store.extend(prepared)
        logger.warning("backfilled %d synthetic log entries", written)
        return {"written": written, "logged_requests": len(store), "source": store.source()}

    return app


app = create_app()
