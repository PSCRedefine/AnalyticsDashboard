# API Reference

Base URL: `http://127.0.0.1:8000`. Interactive docs at `/docs`.

Every number the dashboard draws comes from requests this process has served.
There is no separate data store: the middleware records, and the two analytics
routes query. Sections 4.4 and 4.5 of [SPEC.md](SPEC.md) define the contract.

---

## Shared query parameters

Both analytics routes take the same window and filters.

| Parameter | Default | Notes |
|---|---|---|
| `start` | `end − 7 days` | ISO 8601. A naive timestamp is read as UTC |
| `end` | now (UTC) | ISO 8601 |
| `endpoint` | — | Exact path, e.g. `/predict` |
| `model_version` | — | Exact match against the logged version |
| `status_code_family` | — | `2xx`, `3xx`, `4xx` or `5xx` |

`end <= start` is **400**, not an empty result. A swapped pair of dates that
returned `[]` would read as "no traffic", which is a different and much more
alarming fact than "you asked for a window that runs backwards".

The window is half-open, `[start, end)`. Consecutive windows therefore tile
without double-counting the boundary — which matters, because `/analytics/summary`
compares a window against the one immediately before it.

> The specification lists `2xx`, `4xx` and `5xx`. `3xx` is accepted as well: it
> is a superset that never rejects a value the specification allows, and a
> redirect family is a legitimate thing to filter on.

---

## `GET /analytics/summary`

This window, the window before it, and the difference.

```bash
curl -s "localhost:8000/analytics/summary?start=2026-04-21T10:30:00Z&end=2026-04-28T10:30:00Z"
```

```json
{
  "source": "in_memory_api_logs",
  "last_updated": "2026-04-28T10:30:00+00:00",
  "start": "2026-04-21T10:30:00+00:00",
  "end": "2026-04-28T10:30:00+00:00",
  "filters": {"endpoint": null, "model_version": null, "status_code_family": null},
  "current":  {"total_requests": 120, "avg_response_time_ms": 24.1,
               "error_rate": 0.0167, "avg_probability": 0.733},
  "previous": {"total_requests": 98,  "avg_response_time_ms": 22.5,
               "error_rate": 0.01,   "avg_probability": 0.701},
  "delta":    {"total_requests": 22,  "avg_response_time_ms": 1.6,
               "error_rate": 0.0067, "avg_probability": 0.032}
}
```

### Nulls mean something

`total_requests` is always a number. The other three are **null when the window
holds nothing**, and so is every `delta` field whose previous side is null.

Zero requests is a count. It is not an average response time of `0.0 ms`, and
reporting it as one would put a line at the bottom of the latency chart that
reads as "very fast" instead of "nothing happened". The page renders null as
`-`, and omits a delta rather than showing `+0` for a comparison nobody made.

`avg_probability` averages only over entries that carry one. A request that
returned 404 never reached the model, so counting it as a zero would drag the
model-drift chart down every time a client sent a bad identifier.

### `error_rate` is a fraction

`0.0167`, not `1.67`. The page multiplies by 100 for display; doing it on both
sides would produce 167%.

Anything that is not a 2xx counts (specification 4.5 step 10). A 404 is the
caller's mistake and a 500 is ours, but a service suddenly returning 404 to
everyone is not healthy either. Use `status_code_family` when you need them
apart.

---

## `GET /analytics/timeseries`

The same window, bucketed.

| Parameter | Default | Notes |
|---|---|---|
| `interval` | `1h` | `30s`, `5min`, `1h`, `1d` … Invalid is a **400** |

```json
{
  "source": "in_memory_api_logs",
  "last_updated": "2026-04-28T10:30:00+00:00",
  "start": "2026-04-21T10:30:00+00:00",
  "end": "2026-04-28T10:30:00+00:00",
  "interval": "1h",
  "data": [
    {"timestamp": "2026-04-28T08:00:00+00:00", "requests": 12,
     "avg_response_time_ms": 19.2, "error_rate": 0.0,    "avg_probability": 0.721},
    {"timestamp": "2026-04-28T09:00:00+00:00", "requests": 15,
     "avg_response_time_ms": 25.6, "error_rate": 0.0667, "avg_probability": 0.744}
  ]
}
```

Rows are oldest first, and **empty buckets keep their place**: `requests` becomes
0 and the three averages become null. Dropping them would join the line straight
across a gap and hide an outage, which is the single most important thing a
traffic chart has to show.

Buckets span the first and last request in the window, not the whole window.
Asking for seven days when the log holds an hour of traffic returns that hour,
not six days of leading zeroes.

`5m` means five **minutes**. Pandas reads a bare `m` as month-end, so the parser
maps it explicitly rather than letting `5m` quietly become five months.

An interval that would produce more than 20,000 buckets over the requested span
is a **400**. No line chart renders that usefully, and no browser enjoys
receiving it.

---

## `source`, and why it is not a constant

`in_memory_api_logs` means every entry in the window was produced by a request
this service actually served.

`in_memory_api_logs+synthetic_backfill` means at least one was not. The
dashboard turns that into a warning banner. The field is computed per window
rather than per process, so a backfill from last month does not taint today.

A Data Source field that always says the same thing cannot tell you that you
are looking at a demo, which is the only reason to put one on the page.

---

## `POST /analytics/backfill`

Development only, and **disabled unless `ANALYTICS_ALLOW_BACKFILL=1`** — 404
otherwise. Injects historical entries so the trend charts have a week to draw
before any real traffic exists. Everything it writes is flagged `synthetic`,
which is what flips `source`.

```bash
ANALYTICS_ALLOW_BACKFILL=1 uvicorn analytics_dashboard.api:app
python scripts/backfill_history.py --days 14
```

---

## `POST /predict`

One scored interaction — and the source of every `avg_probability` on the page.

```bash
curl -s -X POST localhost:8000/predict -H 'content-type: application/json' \
  -d '{"user_id":"user_000001","video_id":"video_0000001","watch_time":45,"hour_of_day":14}'
```

| Status | Meaning |
|---|---|
| 200 | Scored |
| 404 | Identifier is well formed but not in the lookup tables |
| 422 | Malformed identifier or out-of-range `watch_time` |
| 503 | Model or lookup tables not loaded |

The route writes `probability` and `model_version` onto `request.state`, and the
middleware reads them back after the response exists (specification 4.3). Those
are business facts the transport layer has no way to observe on its own.

---

## `GET /health`

```json
{"status": "healthy", "model_loaded": true, "store_loaded": true,
 "logged_requests": 24186, "log_capacity": 200000, "uptime_seconds": 122.0,
 "model_name": "logistic_regression_pipeline", "version": "1.0.0", "timestamp": "..."}
```

Not logged. A Docker healthcheck every ten seconds would otherwise contribute
8,640 requests a day of pure noise to the traffic chart it is supposed to be
protecting.
