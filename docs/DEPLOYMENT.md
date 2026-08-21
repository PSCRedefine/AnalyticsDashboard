# Deployment

## Docker

```bash
docker compose up --build
```

API on 8000, dashboard on 8501. The dashboard waits on a healthcheck that tests
`model_loaded` rather than just the port.

**One worker, deliberately.** The request log lives in this process's memory, so
a second worker would hold a second, disjoint log and the dashboard would show
whichever one the load balancer happened to route it to. `--workers 1` is a
correctness constraint here, not a capacity choice —
[ANALYTICS.md](ANALYTICS.md#in-memory-and-what-that-costs) has the full
argument and what it would take to lift it.

## Without Docker

```bash
python -m pip install -r requirements-dev.txt
python -m pip install -e .
uvicorn analytics_dashboard.api:app --reload     # terminal 1
streamlit run app.py                              # terminal 2
```

The log starts empty, so the page opens on its empty state. Fill it:

```bash
python scripts/seed_traffic.py --requests 1000
```

That makes a thousand real calls, three per cent of them deliberately malformed
so the error-rate chart has something to draw. Every entry it produces is real
traffic, and `source` stays `in_memory_api_logs`.

For a full week of history, see the backfill tool below.

## Configuration

| Variable | Default | Used by |
|---|---|---|
| `ANALYTICS_API_URL` | `http://127.0.0.1:8000` | Dashboard |
| `ANALYTICS_ALLOW_BACKFILL` | unset (off) | API — enables the demonstration route |
| `ANALYTICS_MODEL_PATH` | `models/best_model.joblib` | API |
| `ANALYTICS_METADATA_PATH` | `models/model_metadata.json` | API |
| `ANALYTICS_USERS_PATH` | `data/users.csv` | API |
| `ANALYTICS_VIDEOS_PATH` | `data/videos.csv` | API |

## The backfill tool

```bash
ANALYTICS_ALLOW_BACKFILL=1 uvicorn analytics_dashboard.api:app
python scripts/backfill_history.py --days 14
```

Fills the last fourteen days with synthetic hourly traffic, so both the current
window and the one it is compared against have data and every KPI card shows a
delta.

Off by default, and everything it writes is flagged: any window containing a
backfilled entry reports `in_memory_api_logs+synthetic_backfill`, and the page
renders a warning banner saying so. **Never enable it in production** — not
because it is dangerous, but because a monitoring page that can be written to
is not a monitoring page.

## Operating notes

- **A deploy resets the dashboard.** The log is in memory. This is expected;
  it is also why `Last Updated` is on the page.
- **`/health` is not logged.** A ten-second healthcheck would otherwise
  contribute 8,640 requests a day of noise. The exclusion list is
  `config.EXCLUDED_PATHS`.
- **Alerts evaluate the window average.** A one-day incident inside a seven-day
  window can stay below both thresholds while being obvious in the charts. Read
  the charts during an incident, not the cards.
- **Memory is bounded at 200,000 entries**, roughly 40 MB. Past that the oldest
  entry falls out. `/health` reports `logged_requests` against `log_capacity`,
  so the headroom is visible without guessing.
