import logging.config
from src.filesystem.adapters.local_storage import LocalStorage
from src.filesystem.adapters.s3_storage import S3Storage
from src.filesystem.file_manager import FileManager, StorageProvider
from src.config import Config

async def app_boot():
    # Validate config
    Config.validate()

    # Configure logging
    logging.config.dictConfig(Config.LOGGING)

    # Suppress noisy third-party loggers
    # logging.getLogger('openai').setLevel(logging.WARNING)
    
    # File system setup
    file_manager = FileManager()
    local_storage = LocalStorage(Config.LOCAL_STORAGE_FULL_PATH)
    s3_storage = S3Storage()
    
    await file_manager.add_provider(StorageProvider.S3, s3_storage, set_as_default=Config.DEFAULT_FILESYSTEM == StorageProvider.S3.value)
    await file_manager.add_provider(StorageProvider.LOCAL, local_storage, set_as_default=Config.DEFAULT_FILESYSTEM == StorageProvider.LOCAL.value)
    
    logger = logging.getLogger(__name__)
    logger.info(f"App ({Config.APP_NAME}) booted in {Config.APP_MODE} mode")
    
