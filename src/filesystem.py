from concurrent.futures import ThreadPoolExecutor
import boto3
from .config import Config
from botocore.exceptions import ClientError

class FileSystemService:
    def __init__(self):
        self.input_file = self.output_file = self.temp_dir = None
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        
        try:
            self.s3_client = boto3.client(
                's3',
                region_name=Config.DO_SPACES_REGION,
                endpoint_url=Config.DO_SPACES_ENDPOINT,
                aws_access_key_id=Config.DO_SPACES_KEY,
                aws_secret_access_key=Config.DO_SPACES_SECRET
            )
            # Test connection by listing buckets
            self.s3_client.list_buckets()
        except ClientError as e:
            raise ConnectionError(f"Failed to connect to DigitalOcean Spaces: {str(e)}")
        except Exception as e:
            raise Exception(f"Unexpected error when connecting to DigitalOcean Spaces: {str(e)}")