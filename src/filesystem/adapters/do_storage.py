import boto3
from botocore.exceptions import ClientError
from src.config import Config
from src.filesystem.cloud_storage_interface import CloudStorageInterface
from botocore.exceptions import ClientError
from mypy_boto3_s3.client import S3Client

class DOSpacesStorage(CloudStorageInterface):
    """Amazon S3 storage implementation."""
    
    def __init__(self, bucket_name: str, aws_access_key_id: str, aws_secret_access_key: str, region_name: str = 'us-east-1'):
        self.bucket_name = bucket_name
        try:
            self.client: S3Client = boto3.client( # type: ignore[assignment]
                's3',
                region_name=Config.DO_SPACES_REGION,
                endpoint_url=Config.DO_SPACES_ENDPOINT,
                aws_access_key_id=Config.DO_SPACES_KEY,
                aws_secret_access_key=Config.DO_SPACES_SECRET
            )
            # Test connection by listing buckets
            self.client.list_buckets()
        except ClientError as e:
            raise ConnectionError(f"Failed to connect to DigitalOcean Spaces: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error when connecting to DigitalOcean Spaces: {str(e)}")