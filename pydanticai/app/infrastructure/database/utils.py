"""SQLite + SQLAlchemy round-trips every `DateTime(timezone=True)` value as
naive (tzinfo stripped), even though the value written was UTC-aware -
verified empirically (SQLite has no native tz-aware datetime type). Every
column in this schema is written as UTC, so any naive datetime read back
from the DB is UTC and must be tagged explicitly before arithmetic or
serialization - never `.astimezone()` a value that's already naive-UTC,
that reinterprets it as local system time.
"""
from __future__ import annotations

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
