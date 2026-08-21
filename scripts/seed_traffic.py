"""Drive real traffic through the API so the dashboard has something to show.

The request log is in memory and starts empty on every restart, so a freshly
started service renders the empty state — correctly, and unhelpfully. This
script fixes that the honest way: by actually calling the service. Every entry
the dashboard then shows was produced by a request that really happened, and
`source` stays `in_memory_api_logs`.

A slice of the calls are malformed on purpose, because a monitoring page whose
error-rate chart has only ever drawn a flat zero has not been tested.

    python scripts/seed_traffic.py --requests 2000 --error-rate 0.03
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


def identifiers() -> tuple[list[str], list[str]]:
    users = pd.read_csv(DATA_DIR / "users.csv", usecols=["user_id"])["user_id"].astype(str)
    videos = pd.read_csv(DATA_DIR / "videos.csv", usecols=["video_id"])["video_id"].astype(str)
    return users.tolist(), videos.tolist()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send real prediction traffic to the API")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--error-rate", type=float, default=0.03,
                        help="fraction of calls made deliberately invalid")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds between calls")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    random.seed(args.seed)
    api = args.api.rstrip("/")
    try:
        health = requests.get(f"{api}/health", timeout=10).json()
    except requests.RequestException as exc:
        print(f"cannot reach {api}: {exc}", file=sys.stderr)
        return 1
    if not health.get("model_loaded"):
        print(f"{api} is up but has no model loaded; predictions would all 503", file=sys.stderr)
        return 1

    users, videos = identifiers()
    counts: dict[int, int] = {}
    started = time.perf_counter()
    for index in range(args.requests):
        payload = {
            "user_id": random.choice(users),
            "video_id": random.choice(videos),
            "watch_time": round(random.uniform(0, 180), 1),
            "hour_of_day": random.randrange(24),
        }
        if random.random() < args.error_rate:
            # Two distinct failures: an identifier that resolves to nothing
            # (404) and one that is not an identifier at all (422). A chart
            # drawn from only one of them is a chart with a blind spot.
            if random.random() < 0.5:
                payload["user_id"] = "user_999999999"
            else:
                payload["watch_time"] = 99999.0
        try:
            response = requests.post(f"{api}/predict", json=payload, timeout=30)
            counts[response.status_code] = counts.get(response.status_code, 0) + 1
        except requests.RequestException as exc:
            print(f"request {index} failed at the transport layer: {exc}", file=sys.stderr)
        if args.delay:
            time.sleep(args.delay)

    elapsed = time.perf_counter() - started
    breakdown = "  ".join(f"{code}: {count}" for code, count in sorted(counts.items()))
    print(f"sent {args.requests} requests in {elapsed:.1f}s  ({breakdown})")
    print(f"open the dashboard, or: curl -s {api}/analytics/summary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
