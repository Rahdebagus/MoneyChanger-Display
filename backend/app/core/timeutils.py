"""Timestamps are stored in UTC and rendered in the branch timezone.

Bali has no DST, but the conversion still goes through ZoneInfo rather than a
fixed +08:00 offset so a branch in another zone works without code changes.
"""

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import get_settings


def utcnow() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalise a value read back from the database to aware UTC.

    MySQL/MariaDB DATETIME columns come back naive; they were written as UTC,
    so attach UTC rather than assuming the server's local zone.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Strip tzinfo for storage in a DATETIME column, converting to UTC first."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def get_zone(name: Optional[str] = None) -> ZoneInfo:
    settings = get_settings()
    candidate = name or settings.display_timezone
    try:
        return ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def to_display_timezone(value: Optional[datetime], tz_name: Optional[str] = None) -> Optional[datetime]:
    aware = as_utc(value)
    if aware is None:
        return None
    return aware.astimezone(get_zone(tz_name))
