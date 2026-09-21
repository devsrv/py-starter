import hashlib
from datetime import UTC, datetime

from src.config import Config


def get_md5(input_string: str | bytes) -> str:
    """Return the hex MD5 digest of a string or bytes."""
    input_bytes = input_string.encode("utf-8") if isinstance(input_string, str) else input_string
    return hashlib.md5(input_bytes, usedforsecurity=False).hexdigest()


def now() -> datetime:
    """Get current datetime in application timezone"""
    return datetime.now(Config.TZ)


def utcnow() -> datetime:
    """Get current UTC datetime"""
    return datetime.now(UTC)


def to_app_timezone(dt: datetime) -> datetime:
    """Convert datetime to application timezone. Naive datetimes are treated as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(Config.TZ)
