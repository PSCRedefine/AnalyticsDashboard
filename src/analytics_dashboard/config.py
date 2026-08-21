"""Paths, limits and environment-backed settings."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"


def env_path(name: str, default: Path) -> Path:
    """Return an absolute path from an environment variable or a project default."""
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


USERS_PATH = env_path("ANALYTICS_USERS_PATH", DATA_DIR / "users.csv")
VIDEOS_PATH = env_path("ANALYTICS_VIDEOS_PATH", DATA_DIR / "videos.csv")
MODEL_PATH = env_path("ANALYTICS_MODEL_PATH", MODELS_DIR / "best_model.joblib")
METADATA_PATH = env_path("ANALYTICS_METADATA_PATH", MODELS_DIR / "model_metadata.json")

API_BASE_URL = os.getenv("ANALYTICS_API_URL", "http://127.0.0.1:8000")

# Specification 4.2 step 13. At roughly 200 bytes per entry this is about 40 MB
# of resident memory, which is the price of holding a week of traffic for a
# service doing a few requests per second. It is a ring buffer: the oldest entry
# is dropped, never the newest, so a burst cannot blind the dashboard to what is
# happening now.
LOG_CAPACITY = 200_000

# Paths that describe the service rather than use it. Logging them would make
# every dashboard refresh inflate the request count it is reporting
# (specification 4.2 step 3).
EXCLUDED_PREFIXES = ("/analytics",)
EXCLUDED_PATHS = ("/", "/docs", "/redoc", "/openapi.json", "/favicon.ico", "/health")

# Defaults for both analytics routes (specification 4.4 and 4.5).
DEFAULT_WINDOW_DAYS = 7
DEFAULT_INTERVAL = "1h"

# Specification 3.5. Thresholds live here rather than in the page so the page
# and any future alerting rule read the same numbers.
ERROR_RATE_ALERT = 0.02
RESPONSE_TIME_ALERT_MS = 300.0
PROBABILITY_DRIFT_ALERT = 0.1

REQUEST_TIMEOUT_SECONDS = 30
