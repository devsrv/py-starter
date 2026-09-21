from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from src.config import Config
from src.utils import get_md5, now, to_app_timezone, utcnow


def test_get_md5_str_and_bytes():
    assert get_md5("hello") == "5d41402abc4b2a76b9719d911017c592"
    assert get_md5(b"hello") == get_md5("hello")
    assert get_md5("") == "d41d8cd98f00b204e9800998ecf8427e"


def test_now_is_in_app_timezone():
    dt = now()
    assert dt.tzinfo == Config.TZ
    assert abs((dt - datetime.now(Config.TZ)).total_seconds()) < 2


def test_utcnow_is_utc():
    dt = utcnow()
    assert dt.tzinfo == UTC
    assert dt.utcoffset() == timedelta(0)


def test_to_app_timezone_converts_aware():
    src = datetime(2025, 1, 1, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    out = to_app_timezone(src)
    assert out.tzinfo == Config.TZ
    assert out == src  # same instant


def test_to_app_timezone_treats_naive_as_utc():
    naive = datetime(2025, 6, 1, 12, 0)
    out = to_app_timezone(naive)
    assert out == naive.replace(tzinfo=UTC)
    assert out.hour == 8  # New York is UTC-4 in June
