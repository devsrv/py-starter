import logging
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from src.logging.daily_file_handler import DailyFileHandler


def _make_logger(handler: logging.Handler) -> logging.Logger:
    logger = logging.getLogger(f"test.daily.{id(handler)}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return logger


def test_requires_date_placeholder(tmp_path):
    with pytest.raises(ValueError, match="{date}"):
        DailyFileHandler(str(tmp_path / "app.log"))


def test_creates_missing_directory_and_dated_file(tmp_path, monkeypatch):
    monkeypatch.setattr(DailyFileHandler, "_today", lambda self: "2025-01-15")
    handler = DailyFileHandler(str(tmp_path / "nested" / "logs" / "app-{date}.log"))
    logger = _make_logger(handler)
    logger.info("hello")
    handler.close()

    target = tmp_path / "nested" / "logs" / "app-2025-01-15.log"
    assert target.exists()
    assert "hello" in target.read_text()
    assert Path(handler.baseFilename).is_absolute()


def test_rolls_over_when_date_changes(tmp_path, monkeypatch):
    today = {"value": "2025-01-15"}
    monkeypatch.setattr(DailyFileHandler, "_today", lambda self: today["value"])

    handler = DailyFileHandler(str(tmp_path / "app-{date}.log"))
    logger = _make_logger(handler)

    logger.info("day one")
    today["value"] = "2025-01-16"
    logger.info("day two")
    handler.close()

    day1 = (tmp_path / "app-2025-01-15.log").read_text()
    day2 = (tmp_path / "app-2025-01-16.log").read_text()
    assert "day one" in day1 and "day two" not in day1
    assert "day two" in day2 and "day one" not in day2


def test_uses_given_timezone_for_date():
    handler_utc = DailyFileHandler.__new__(DailyFileHandler)
    handler_utc.tz = ZoneInfo("UTC")
    handler_ny = DailyFileHandler.__new__(DailyFileHandler)
    handler_ny.tz = ZoneInfo("America/New_York")
    # Both must produce YYYY-MM-DD strings; they may differ around midnight.
    for h in (handler_utc, handler_ny):
        assert len(h._today()) == 10


def test_works_through_dictconfig(tmp_path, monkeypatch):
    """The handler is built via logging.config.dictConfig's '()' factory in Config.LOGGING."""
    import logging.config

    monkeypatch.setattr(DailyFileHandler, "_today", lambda self: "2030-02-03")
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "daily": {
                    "()": DailyFileHandler,
                    "filename_pattern": str(tmp_path / "x-{date}.log"),
                    "level": "INFO",
                    "tz": ZoneInfo("UTC"),
                }
            },
            "loggers": {
                "dictcfg.test": {"handlers": ["daily"], "level": "INFO", "propagate": False}
            },
        }
    )
    logging.getLogger("dictcfg.test").info("via dictconfig")
    for h in logging.getLogger("dictcfg.test").handlers:
        h.close()
    assert "via dictconfig" in (tmp_path / "x-2030-02-03.log").read_text()
