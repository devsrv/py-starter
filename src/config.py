import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from src.filesystem.providers import StorageProvider
from src.logging.daily_file_handler import DailyFileHandler

load_dotenv()

_TRUE = {"1", "true", "yes", "on", "y", "t"}
_FALSE = {"0", "false", "no", "off", "n", "f"}


def env_str(name: str, default: str = "") -> str:
    """Read a string env var. Empty values fall back to the default."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def env_bool(name: str, default: bool | None = None) -> bool | None:
    """Read a boolean env var strictly. Unset/empty returns the default."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    val = value.strip().lower()
    if val in _TRUE:
        return True
    if val in _FALSE:
        return False
    msg = f"{name}={value!r} is not a boolean. Use one of {sorted(_TRUE)} or {sorted(_FALSE)}."
    raise ValueError(msg)


def env_int(name: str, default: int) -> int:
    """Read an integer env var. Unset/empty returns the default."""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value.strip())
    except ValueError as e:
        msg = f"{name}={value!r} is not an integer."
        raise ValueError(msg) from e


class Config:
    # Project root (the directory that holds app.py / boot.py)
    BASE_DIR = Path(__file__).resolve().parent.parent

    APP_NAME = env_str("APP_NAME", "My APP")
    APP_MODE = env_str("APP_MODE", "development").lower()
    APP_DEBUG = env_bool("APP_DEBUG", default=True)
    DEBUG = APP_MODE != "production" and bool(APP_DEBUG)

    TZ = ZoneInfo(env_str("TZ", "America/New_York"))

    # Everything the app writes on disk lives under STORAGE_DIR
    STORAGE_DIR = Path(env_str("STORAGE_DIR", str(BASE_DIR / "storage")))
    LOG_DIR = STORAGE_DIR / "logs"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

    LOGGING: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "level": LOG_LEVEL,
                "formatter": "detailed" if DEBUG else "standard",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "file_daily": {
                "()": DailyFileHandler,
                "filename_pattern": str(LOG_DIR / "app-{date}.log"),
                "level": "INFO",
                "formatter": "standard",
                "encoding": "utf-8",
                "tz": TZ,
            },
            "error_daily": {
                "()": DailyFileHandler,
                "filename_pattern": str(LOG_DIR / "error-{date}.log"),
                "level": "ERROR",
                "formatter": "detailed",
                "encoding": "utf-8",
                "tz": TZ,
            },
        },
        "loggers": {
            "": {  # Root logger
                "handlers": ["console", "file_daily", "error_daily"],
                "level": "DEBUG" if DEBUG else "INFO",
            },
            "fastapi": {
                "handlers": ["console", "file_daily"],
                "level": "INFO",
                "propagate": False,
            },
            "pymongo": {  # MongoDB driver logs
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "motor": {  # Motor async driver
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }

    DEFAULT_FILESYSTEM = env_str("DEFAULT_FILESYSTEM", "local").lower()

    DO_SPACES_KEY = env_str("DO_SPACES_KEY")
    DO_SPACES_SECRET = env_str("DO_SPACES_SECRET")
    DO_SPACES_REGION = env_str("DO_SPACES_REGION", "nyc3")
    DO_SPACES_BUCKET = env_str("DO_SPACES_BUCKET")

    MINIO_BUCKET = env_str("MINIO_BUCKET")
    MINIO_ENDPOINT = env_str("MINIO_ENDPOINT", "http://localhost:9000")
    MINIO_ACCESS_KEY = env_str("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY = env_str("MINIO_SECRET_KEY")

    AWS_ACCESS_KEY_ID = env_str("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env_str("AWS_SECRET_ACCESS_KEY")
    AWS_REGION_NAME = env_str("AWS_REGION_NAME", "us-east-1")
    AWS_S3_BUCKET_NAME = env_str("AWS_S3_BUCKET_NAME")

    # Local storage lives inside STORAGE_DIR/app/<LOCAL_STORAGE_PATH>
    LOCAL_STORAGE_PATH = env_str("LOCAL_STORAGE_PATH", "media")
    LOCAL_STORAGE_FULL_PATH = str(STORAGE_DIR / "app" / LOCAL_STORAGE_PATH)

    MONGO_URI = env_str("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = env_str("MONGO_DB_NAME", "app")
    # None -> let the URI decide (mongodb+srv:// implies TLS). True/False -> force.
    MONGO_TLS: bool | None = env_bool("MONGO_TLS", default=None)

    MYSQL_HOST = env_str("MYSQL_HOST", "localhost")
    MYSQL_PORT = env_int("MYSQL_PORT", 3306)
    MYSQL_USER = env_str("MYSQL_USER", "root")
    MYSQL_DB = env_str("MYSQL_DB", "test")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")

    REDIS_HOST = env_str("REDIS_HOST", "localhost")
    REDIS_PORT = env_int("REDIS_PORT", 6379)
    REDIS_DB = env_int("REDIS_DB", 0)
    REDIS_PASSWORD: str | None = os.getenv("REDIS_PASSWORD") or None

    HTTP_SECRET: str | None = os.getenv("HTTP_SECRET") or None

    GOOGLE_CHAT_DEV_TEAM_WEBHOOK: str = env_str("GOOGLE_CHAT_DEV_TEAM_WEBHOOK")

    # CORS configuration (comma separated)
    ALLOWED_ORIGINS = env_str("ALLOWED_ORIGINS")

    # Concurrency configuration
    MAX_CONCURRENT_TASKS = env_int("MAX_CONCURRENT_TASKS", 5)

    @classmethod
    def allowed_origins(cls) -> list[str]:
        """Parse ALLOWED_ORIGINS. In non-production an empty value means allow all."""
        origins = [o.strip() for o in cls.ALLOWED_ORIGINS.split(",") if o.strip()]
        if not origins and cls.APP_MODE != "production":
            return ["*"]
        return origins

    @classmethod
    def validate(cls) -> None:
        """Validate critical configuration. Raises ValueError with every problem found."""
        errors: list[str] = []

        storage_providers = sorted(storage.value for storage in StorageProvider)
        if cls.DEFAULT_FILESYSTEM not in storage_providers:
            errors.append(
                f"Invalid DEFAULT_FILESYSTEM: {cls.DEFAULT_FILESYSTEM}. "
                f"Must be one of {storage_providers}"
            )

        if cls.APP_MODE not in ("development", "production"):
            errors.append(
                f"Invalid APP_MODE: {cls.APP_MODE}. Must be 'development' or 'production'"
            )

        if cls.APP_MODE == "production":
            if not cls.HTTP_SECRET:
                errors.append("HTTP_SECRET is required in production")
            if not cls.ALLOWED_ORIGINS:
                errors.append("ALLOWED_ORIGINS is required in production")

        if errors:
            msg = f"Configuration errors: {'; '.join(errors)}"
            raise ValueError(msg)

    @classmethod
    def get_absolute_path(cls, relative_path: str) -> Path:
        """Resolve a path relative to the project root."""
        return cls.BASE_DIR / relative_path
