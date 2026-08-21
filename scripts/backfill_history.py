"""Inject a week of synthetic history so the trend charts have a week to draw.

`seed_traffic.py` produces real entries, but they all land in the minute you ran
it, so a seven-day window shows one bucket. This script fills the days before
now with entries that no client ever sent.

That is a demonstration aid, and the code treats it as one. The service refuses
the route unless `ANALYTICS_ALLOW_BACKFILL=1`, every entry it writes is flagged
`synthetic`, and any window containing one reports its source as
`in_memory_api_logs+synthetic_backfill` — which the page renders as a warning
banner. Fabricated data is fine as long as nothing ever claims it is real.

    ANALYTICS_ALLOW_BACKFILL=1 uvicorn analytics_dashboard.api:app
    python scripts/backfill_history.py --days 7
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from datetime import UTC, datetime, timedelta

import requests

# The served model's outputs sit in a narrow band around the base rate rather
# than spanning [0, 1]; synthesised probabilities that ignored that would make
# the drift chart look nothing like the real one.
BASE_PROBABILITY = 0.28
BASE_RESPONSE_MS = 22.0


def generate(days: int, per_hour: int, seed: int) -> list[dict]:
    """One entry per request, over `days` of hourly buckets ending now.

    Traffic follows a daily rhythm — a quiet trough overnight, a broad afternoon
    peak — because a flat line would not exercise the thing the Requests chart
    exists to show.
    """
    random.seed(seed)
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    entries: list[dict] = []
    for hours_ago in range(days * 24, 0, -1):
        bucket = now - timedelta(hours=hours_ago)
        rhythm = 0.65 + 0.35 * math.sin((bucket.hour - 4) / 24 * 2 * math.pi)
        count = max(1, int(per_hour * rhythm * random.uniform(0.85, 1.15)))
        latency = BASE_RESPONSE_MS * random.uniform(0.8, 1.4)
        error_rate = max(0.0, random.gauss(0.012, 0.008))
        drift = 0.03 * math.sin(hours_ago / 40)
        for _ in range(count):
            failed = random.random() < error_rate
            entries.append({
                "timestamp": (bucket + timedelta(seconds=random.randrange(3600))).isoformat(),
                "endpoint": "/predict",
                "status_code": random.choice([404, 422, 500]) if failed else 200,
                "response_time_ms": round(max(1.0, random.gauss(latency, latency * 0.3)), 3),
                "model_version": "1.0.0",
                # A failed request never reached the model, so it has no
                # probability — the same shape a real error entry has.
                "probability": None if failed else round(
                    min(0.999, max(0.001, random.gauss(BASE_PROBABILITY + drift, 0.05))), 6
                ),
            })
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill synthetic request history")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--per-hour", type=int, default=110)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)

    entries = generate(args.days, args.per_hour, args.seed)
    api = args.api.rstrip("/")
    try:
        response = requests.post(f"{api}/analytics/backfill", json=entries, timeout=120)
    except requests.RequestException as exc:
        print(f"cannot reach {api}: {exc}", file=sys.stderr)
        return 1
    if response.status_code == 404:
        print("the backfill route is disabled. Restart the API with "
              "ANALYTICS_ALLOW_BACKFILL=1 to enable it.", file=sys.stderr)
        return 1
    if not response.ok:
        print(f"backfill failed: HTTP {response.status_code} {response.text}", file=sys.stderr)
        return 1

    body = response.json()
    print(f"backfilled {body['written']:,} synthetic entries over {args.days} days")
    print(f"the log now holds {body['logged_requests']:,} entries; source = {body['source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
