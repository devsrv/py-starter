import logging
from datetime import datetime, tzinfo
from pathlib import Path


class DailyFileHandler(logging.FileHandler):
    """Custom handler that creates a new log file each day with the date in the filename.

    `filename_pattern` must contain a `{date}` placeholder, e.g. 'logs/app-{date}.log'.
    `tz` controls which timezone decides when a "day" rolls over (defaults to local time).
    """

    def __init__(
        self,
        filename_pattern: str,
        mode: str = "a",
        encoding: str | None = "utf-8",
        delay: bool = False,
        tz: tzinfo | None = None,
    ):
        if "{date}" not in filename_pattern:
            msg = "filename_pattern must contain a {date} placeholder"
            raise ValueError(msg)
        self.filename_pattern = filename_pattern
        self.tz = tz
        self.current_date = self._today()

        filename = self._get_current_filename()
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        super().__init__(filename, mode, encoding, delay)

    def _today(self) -> str:
        return datetime.now(self.tz).strftime("%Y-%m-%d")

    def _get_current_filename(self) -> str:
        """Generate the absolute filename for the current date."""
        return str(Path(self.filename_pattern.format(date=self.current_date)).resolve())

    def emit(self, record: logging.LogRecord) -> None:
        """Switch to a new file when the date changes, then emit normally."""
        today = self._today()
        if today != self.current_date:
            self._rollover(today)
        super().emit(record)

    def _rollover(self, today: str) -> None:
        self.acquire()
        try:
            if self.stream and not self.stream.closed:
                self.stream.close()
            self.current_date = today
            self.baseFilename = self._get_current_filename()
            Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
            # FileHandler reopens the stream lazily when it is None
            self.stream = None  # type: ignore[assignment]
        finally:
            self.release()
