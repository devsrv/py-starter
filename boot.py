"""
Application boot: validates config, wires logging and registers storage providers.

Call `await app_boot()` once at startup. `app.py` does this in the FastAPI lifespan
and `src/app/main.py` does it for standalone scripts.
"""

import logging
import logging.config

from src.config import Config
from src.filesystem.adapters.local_storage import LocalStorage
from src.filesystem.adapters.s3_compatible_storage import S3CompatibleStorage
from src.filesystem.cloud_storage_interface import CloudStorageInterface
from src.filesystem.file_manager import FileManager
from src.filesystem.providers import StorageProvider
from src.utils.performance import performance_tracker

logger = logging.getLogger(__name__)


def build_storage_providers() -> dict[StorageProvider, CloudStorageInterface]:
    """Instantiate every storage provider that has credentials configured.

    Local storage is always available. Cloud providers are only registered when
    their access keys are present, so an empty `.env` still boots.
    """
    providers: dict[StorageProvider, CloudStorageInterface] = {
        StorageProvider.LOCAL: LocalStorage(Config.LOCAL_STORAGE_FULL_PATH),
    }

    if Config.AWS_ACCESS_KEY_ID and Config.AWS_SECRET_ACCESS_KEY and Config.AWS_S3_BUCKET_NAME:
        providers[StorageProvider.S3] = S3CompatibleStorage(
            bucket_name=Config.AWS_S3_BUCKET_NAME,
            provider="aws",
            region=Config.AWS_REGION_NAME,
            access_key_id=Config.AWS_ACCESS_KEY_ID,
            secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
        )

    if Config.DO_SPACES_KEY and Config.DO_SPACES_SECRET and Config.DO_SPACES_BUCKET:
        providers[StorageProvider.DO_SPACES] = S3CompatibleStorage.for_digitalocean(
            space_name=Config.DO_SPACES_BUCKET,
            region=Config.DO_SPACES_REGION,
            access_key=Config.DO_SPACES_KEY,
            secret_key=Config.DO_SPACES_SECRET,
        )

    if Config.MINIO_ACCESS_KEY and Config.MINIO_SECRET_KEY and Config.MINIO_BUCKET:
        providers[StorageProvider.MINIO] = S3CompatibleStorage.for_minio(
            bucket_name=Config.MINIO_BUCKET,
            endpoint_url=Config.MINIO_ENDPOINT,
            access_key=Config.MINIO_ACCESS_KEY,
            secret_key=Config.MINIO_SECRET_KEY,
        )

    return providers


async def app_boot() -> None:
    performance_tracker.start_boot()

    Config.validate()
    logging.config.dictConfig(Config.LOGGING)

    # Suppress noisy third-party loggers here if needed, e.g.
    # logging.getLogger("botocore").setLevel(logging.WARNING)  # noqa: ERA001

    providers = build_storage_providers()
    default = StorageProvider(Config.DEFAULT_FILESYSTEM)
    if default not in providers:
        msg = (
            f"DEFAULT_FILESYSTEM is '{default.value}' but its credentials are not configured. "
            f"Configured providers: {sorted(p.value for p in providers)}"
        )
        raise ValueError(msg)

    file_manager = FileManager()
    await FileManager.reset()
    for name, provider in providers.items():
        await file_manager.add_provider(name, provider, set_as_default=name == default)

    performance_tracker.end_boot()

    logger.info("App (%s) booted in %s mode", Config.APP_NAME, Config.APP_MODE)
    logger.info("Storage providers: %s (default: %s)", file_manager.providers, default.value)
    logger.info("Boot completed in %.3f seconds", performance_tracker.get_boot_time() or 0.0)
