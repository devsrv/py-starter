from enum import Enum

class StorageProvider(Enum):
    """Supported storage providers."""
    LOCAL = "local"
    S3 = "s3"
    DO_SPACES = "do_spaces"
    MINIO = "minio"
    # Add more providers as needed, e.g., AZURE, S3_BACKUP etc.