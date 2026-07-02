"""Timezone-aware UTC helpers (Python 3.10+ compatible)."""

from datetime import datetime, timezone

UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
