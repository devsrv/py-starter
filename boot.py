import logging.config
from src.utils.performance import performance_tracker
from src.filesystem.adapters.s3_compatible_storage import S3CompatibleStorage
from src.filesystem.adapters.local_storage import LocalStorage
from src.filesystem.file_manager import FileManager
from src.filesystem.providers import StorageProvider
from src.config import Config


async def app_boot():
    # Start tracking boot time
    performance_tracker.start_boot()
    
    # Validate config
    Config.validate()

    # Configure logging
    logging.config.dictConfig(Config.LOGGING)

    # Suppress noisy third-party loggers
    # logging.getLogger('openai').setLevel(logging.WARNING)
    
    # File system setup
    file_manager = FileManager()
    local_storage = LocalStorage(Config.LOCAL_STORAGE_FULL_PATH)
    s3_storage = S3CompatibleStorage(
        bucket_name=Config.AWS_S3_BUCKET_NAME,
        provider='aws',
        region=Config.AWS_REGION_NAME,
        access_key_id=Config.AWS_ACCESS_KEY_ID,
        secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
    )
    do_spaces_storage = S3CompatibleStorage.for_digitalocean(
        space_name=Config.DO_SPACES_BUCKET,
        region=Config.DO_SPACES_REGION,
        access_key=Config.DO_SPACES_KEY,
        secret_key=Config.DO_SPACES_SECRET,
    )
    minio_storage = S3CompatibleStorage.for_minio(
        bucket_name=Config.MINIO_BUCKET,
        endpoint_url=Config.MINIO_ENDPOINT,
        access_key=Config.MINIO_ACCESS_KEY,
        secret_key=Config.MINIO_SECRET_KEY,
    )
    
    await file_manager.add_provider(StorageProvider.S3, s3_storage, set_as_default=Config.DEFAULT_FILESYSTEM == StorageProvider.S3.value)
    await file_manager.add_provider(StorageProvider.DO_SPACES, do_spaces_storage, set_as_default=Config.DEFAULT_FILESYSTEM == StorageProvider.DO_SPACES.value)
    await file_manager.add_provider(StorageProvider.MINIO, minio_storage, set_as_default=Config.DEFAULT_FILESYSTEM == StorageProvider.MINIO.value)
    await file_manager.add_provider(StorageProvider.LOCAL, local_storage, set_as_default=Config.DEFAULT_FILESYSTEM == StorageProvider.LOCAL.value)
    
    # Mark boot as complete
    performance_tracker.end_boot()
    
    # Sratup complete
    logger = logging.getLogger(__name__)
    logger.info(f"App ({Config.APP_NAME}) booted in {Config.APP_MODE} mode")
    logger.info(f"Boot completed in {performance_tracker.get_boot_time():.3f} seconds")
    
