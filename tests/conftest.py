"""
Shared fixtures.

Config reads the environment at import time, so the test environment is pinned
here BEFORE anything from `src` is imported. Values set in os.environ win over a
local `.env` file (python-dotenv never overrides existing variables).
"""

import os
import tempfile
from pathlib import Path

_TEST_STORAGE = Path(tempfile.mkdtemp(prefix="py-starter-tests-"))

os.environ.update(
    {
        "APP_NAME": "Test App",
        "APP_MODE": "development",
        "APP_DEBUG": "true",
        "TZ": "America/New_York",
        "STORAGE_DIR": str(_TEST_STORAGE),
        "DEFAULT_FILESYSTEM": "local",
        "LOCAL_STORAGE_PATH": "media",
        "HTTP_SECRET": "test-secret",
        "ALLOWED_ORIGINS": "",
        "GOOGLE_CHAT_DEV_TEAM_WEBHOOK": "",
        "MONGO_URI": "mongodb://localhost:27017",
        "MONGO_DB_NAME": "test_db",
        "MONGO_TLS": "",
        "MYSQL_PORT": "3306",
        "REDIS_PORT": "6379",
        "REDIS_DB": "0",
        "REDIS_PASSWORD": "",
        # Make sure no real cloud credentials leak in from a developer's .env
        "AWS_ACCESS_KEY_ID": "",
        "AWS_SECRET_ACCESS_KEY": "",
        "AWS_S3_BUCKET_NAME": "",
        "DO_SPACES_KEY": "",
        "DO_SPACES_SECRET": "",
        "DO_SPACES_BUCKET": "",
        "MINIO_ACCESS_KEY": "",
        "MINIO_SECRET_KEY": "",
        "MINIO_BUCKET": "",
    }
)

import pytest  # noqa: E402

from src.filesystem.adapters.local_storage import LocalStorage  # noqa: E402
from src.filesystem.file_manager import FileManager  # noqa: E402
from src.filesystem.providers import StorageProvider  # noqa: E402


@pytest.fixture
def local_storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(str(tmp_path / "storage"))


@pytest.fixture
async def file_manager(local_storage: LocalStorage):
    """A FileManager with a fresh registry containing one local provider as default."""
    await FileManager.reset()
    fm = FileManager()
    await fm.add_provider(StorageProvider.LOCAL, local_storage, set_as_default=True)
    yield fm
    await FileManager.reset()
