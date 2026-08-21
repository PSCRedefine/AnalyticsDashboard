"""Feature construction for the prediction route.

Shared, unchanged, with the ModelInfo service: the served artefact is the same
`Pipeline`, so the 54 raw columns it was fitted on have to be built the same
way. Duplicating the module rather than importing it keeps this repository
standalone, which is the pattern the whole series follows.

Everything here is servable — derivable from `user_id`, `video_id`,
`watch_time` and a clock, plus the user and video snapshot tables. Columns
observed *during* an interaction, and the five outcome flags that define the
label, are excluded. That exclusion list is inherited from SinglePrediction's
docs/FEATURE_SELECTION.md rather than reinvented.

For this repository the route matters more than the model: `/predict` is what
produces the log entries the Analytics page is built on, and the `probability`
it returns is the only source of the Avg Probability card.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

MAX_WATCH_TIME_SECONDS = 3600.0
USER_ID_PATTERN = re.compile(r"user_[A-Za-z0-9_-]+")
VIDEO_ID_PATTERN = re.compile(r"video_[A-Za-z0-9_-]+")

# Columns that must never reach the model. The first group *is* the label; the
# second is derived from it; the third is known only after the interaction ends.
LEAKING_COLUMNS = [
    "liked", "shared", "commented", "followed_creator", "replayed",
    "engagement_score",
    "skipped_quickly", "scroll_velocity", "sound_on", "time_since_last_interaction",
]

TARGET_COLUMNS = ["liked", "shared", "commented", "followed_creator", "replayed"]

# --- The raw schema --------------------------------------------------------

REQUEST_NUMERIC = [
    "watch_time",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "month",
]

VIDEO_NUMERIC = [
    "duration_seconds",
    "days_since_upload",
    "view_count",
    "like_count",
    "comment_count",
    "share_count",
    "trending_score",
    "avg_watch_time_seconds",
    "retention_rate",
    "engagement_rate",
    "hashtag_count",
    "description_length",
]

USER_NUMERIC = [
    "age",
    "account_age_days",
    "subscriber_count",
    "subscription_count",
    "total_watch_time_minutes",
    "total_video_views",
    "total_likes_given",
    "total_shares_given",
    "total_comments_given",
    "avg_session_length_minutes",
]

DERIVED_NUMERIC = [
    "completion_rate",
    "watch_time_normalized",
    "watch_vs_video_average",
    "user_like_rate",
    "user_share_rate",
    "user_comment_rate",
    "video_like_rate",
    "video_share_rate",
    "video_comment_rate",
    "category_match",
]

RAW_NUMERIC_FEATURES = [*REQUEST_NUMERIC, *VIDEO_NUMERIC, *USER_NUMERIC, *DERIVED_NUMERIC]

RAW_CATEGORICAL_FEATURES = [
    "device_type",
    "platform",
    "gender",
    "country",
    "language",
    "preferred_category",
    "is_premium",
    "category",
    "video_language",
    "video_quality",
    "top_country",
    "has_music",
    "has_text_overlay",
    "has_effects",
    "has_voiceover",
    "is_vertical",
    "is_monetized",
]

RAW_FEATURE_COLUMNS = [*RAW_NUMERIC_FEATURES, *RAW_CATEGORICAL_FEATURES]

USER_COLUMNS = [
    "user_id", "age", "gender", "country", "language", "account_age_days",
    "subscriber_count", "subscription_count", "total_watch_time_minutes",
    "total_video_views", "total_likes_given", "total_shares_given",
    "total_comments_given", "preferred_categories", "avg_session_length_minutes",
    "is_premium", "primary_device", "primary_platform",
]

VIDEO_COLUMNS = [
    "video_id", "category", "duration_seconds", "days_since_upload", "view_count",
    "like_count", "comment_count", "share_count", "has_music", "has_text_overlay",
    "has_effects", "has_voiceover", "is_vertical", "video_quality", "trending_score",
    "avg_watch_time_seconds", "retention_rate", "engagement_rate", "hashtag_count",
    "description_length", "top_country", "is_monetized", "language",
]


def validate_ids(user_id: str, video_id: str) -> None:
    """Validate identifier shape without assuming a fixed digit count."""
    if not USER_ID_PATTERN.fullmatch(str(user_id)):
        raise ValueError(
            "user_id must start with 'user_' and contain only letters, digits, "
            "underscores or hyphens"
        )
    if not VIDEO_ID_PATTERN.fullmatch(str(video_id)):
        raise ValueError(
            "video_id must start with 'video_' and contain only letters, digits, "
            "underscores or hyphens"
        )


def _ratio(numerator: pd.Series, denominator: pd.Series, cap: float | None = None) -> pd.Series:
    """Divide, turning division by zero into a missing value rather than an infinity.

    The imputer downstream understands a missing value. It does not understand
    ``inf``, and neither does ``StandardScaler``: one infinite cell is enough to
    make an entire scaled column NaN.
    """
    denominator = pd.to_numeric(denominator, errors="coerce")
    result = pd.to_numeric(numerator, errors="coerce") / denominator.where(denominator > 0)
    result = result.replace([np.inf, -np.inf], np.nan)
    return result.clip(upper=cap) if cap is not None else result


def _as_flag(series: pd.Series) -> pd.Series:
    """Normalise a CSV boolean into the two strings the encoder will see."""
    return (
        series.astype(str).str.strip().str.lower()
        .map({"true": "true", "false": "false", "1": "true", "0": "false"})
        .fillna("unknown")
    )


def build_raw_features(
    requests: pd.DataFrame, users: pd.DataFrame, videos: pd.DataFrame
) -> pd.DataFrame:
    """Join a request frame against the snapshot tables and derive every raw feature.

    ``requests`` needs ``user_id``, ``video_id``, ``watch_time`` and ``timestamp``.
    Rows whose identifiers do not resolve keep their place and carry missing
    snapshot values — dropping them here would silently change the row count that
    the caller is holding results against.
    """
    frame = requests.copy()
    frame["user_id"] = frame["user_id"].astype(str)
    frame["video_id"] = frame["video_id"].astype(str)
    frame["watch_time"] = pd.to_numeric(frame["watch_time"], errors="coerce")

    stamps = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame["hour_of_day"] = frame.get("hour_of_day", stamps.dt.hour)
    frame["hour_of_day"] = pd.to_numeric(frame["hour_of_day"], errors="coerce")
    frame["day_of_week"] = stamps.dt.dayofweek
    frame["is_weekend"] = (stamps.dt.dayofweek >= 5).astype(float)
    frame["month"] = stamps.dt.month

    frame = frame.merge(
        users[USER_COLUMNS].rename(columns={
            "primary_device": "device_type",
            "primary_platform": "platform",
        }),
        on="user_id", how="left",
    )
    frame = frame.merge(
        videos[VIDEO_COLUMNS].rename(columns={"language": "video_language"}),
        on="video_id", how="left",
    )

    frame["completion_rate"] = _ratio(frame["watch_time"], frame["duration_seconds"], cap=1.0)
    frame["watch_time_normalized"] = _ratio(
        frame["watch_time"], frame["avg_session_length_minutes"] * 60.0
    )
    frame["watch_vs_video_average"] = _ratio(
        frame["watch_time"], frame["avg_watch_time_seconds"]
    )
    frame["user_like_rate"] = _ratio(frame["total_likes_given"], frame["total_video_views"])
    frame["user_share_rate"] = _ratio(frame["total_shares_given"], frame["total_video_views"])
    frame["user_comment_rate"] = _ratio(frame["total_comments_given"], frame["total_video_views"])
    frame["video_like_rate"] = _ratio(frame["like_count"], frame["view_count"])
    frame["video_share_rate"] = _ratio(frame["share_count"], frame["view_count"])
    frame["video_comment_rate"] = _ratio(frame["comment_count"], frame["view_count"])

    preferred = frame["preferred_categories"].fillna("").astype(str)
    frame["preferred_category"] = preferred.str.split(";").str[0].replace("", "unknown")
    frame["category_match"] = [
        float(str(category) in set(filter(None, str(catalogue).split(";"))))
        for category, catalogue in zip(frame["category"], preferred, strict=True)
    ]

    for column in RAW_CATEGORICAL_FEATURES:
        frame[column] = (
            _as_flag(frame[column])
            if column in {"is_premium", "is_monetized", "has_music", "has_text_overlay",
                          "has_effects", "has_voiceover", "is_vertical"}
            else frame[column].astype("string").fillna("unknown").astype(str)
        )
    for column in RAW_NUMERIC_FEATURES:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    return frame[RAW_FEATURE_COLUMNS]


def build_target(interactions: pd.DataFrame) -> pd.Series:
    """``liked OR shared OR commented OR followed_creator OR replayed``.

    The same definition the two earlier services trained against, restated here
    rather than imported so this repository stands alone.
    """
    flags = [
        interactions[column].astype(str).str.strip().str.lower().eq("true")
        for column in TARGET_COLUMNS
    ]
    combined = flags[0]
    for flag in flags[1:]:
        combined = combined | flag
    return combined.astype(int)


@dataclass
class FeatureStore:
    """Identifier resolution and online feature construction.

    Kept deliberately close to ``batch_prediction.features.FeatureStore``: an
    unknown identifier must produce an error rather than a prediction, and the
    snapshot tables supply the columns a request does not carry.
    """

    users: pd.DataFrame
    videos: pd.DataFrame

    def __post_init__(self) -> None:
        self.users = self.users.assign(user_id=self.users["user_id"].astype(str))
        self.videos = self.videos.assign(video_id=self.videos["video_id"].astype(str))
        self.user_ids = set(self.users["user_id"])
        self.video_ids = set(self.videos["video_id"])

    @classmethod
    def from_csv(cls, users_path: str, videos_path: str) -> "FeatureStore":
        users = pd.read_csv(users_path, usecols=USER_COLUMNS)
        videos = pd.read_csv(videos_path, usecols=VIDEO_COLUMNS)
        return cls(users=users, videos=videos)

    def build_one(
        self, user_id: str, video_id: str, watch_time: float, timestamp: pd.Timestamp
    ) -> pd.DataFrame:
        """Single-row raw feature frame for ``/predict``."""
        validate_ids(user_id, video_id)
        user_id, video_id = str(user_id), str(video_id)
        if user_id not in self.user_ids:
            raise KeyError(f"unknown user_id: {user_id}")
        if video_id not in self.video_ids:
            raise KeyError(f"unknown video_id: {video_id}")
        try:
            seconds = float(watch_time)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"watch_time is not a number: {watch_time!r}") from exc
        if seconds != seconds:  # NaN
            raise ValueError("watch_time is not a number: nan")
        if not 0 <= seconds <= MAX_WATCH_TIME_SECONDS:
            raise ValueError(f"watch_time must be between 0 and {MAX_WATCH_TIME_SECONDS:.0f}")
        request = pd.DataFrame([{
            "user_id": user_id,
            "video_id": video_id,
            "watch_time": seconds,
            "timestamp": timestamp,
        }])
        return build_raw_features(request, self.users, self.videos)
