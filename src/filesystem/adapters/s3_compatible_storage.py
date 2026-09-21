import logging
import mimetypes
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, BinaryIO

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from src.config import Config
from src.filesystem.cloud_storage_interface import (
    CloudStorageInterface,
    FileInfo,
    FolderInfo,
)

logger = logging.getLogger(__name__)

# S3 DeleteObjects accepts at most 1000 keys per request
DELETE_BATCH_SIZE = 1000


class S3CompatibleStorage(CloudStorageInterface):
    """S3-compatible storage implementation supporting AWS S3, DigitalOcean Spaces, MinIO, etc."""

    # Predefined endpoints for popular S3-compatible services
    ENDPOINTS: dict[str, str | None] = {
        "aws": None,  # Uses default AWS endpoints
        "digitalocean": "https://{region}.digitaloceanspaces.com",
        "minio": "http://localhost:9000",  # Default MinIO endpoint
        "wasabi": "https://s3.{region}.wasabisys.com",
        "backblaze": "https://s3.{region}.backblazeb2.com",
        "linode": "https://{region}.linodeobjects.com",
    }

    def __init__(
        self,
        bucket_name: str | None = None,
        provider: str = "aws",
        endpoint_url: str | None = None,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        use_ssl: bool = True,
        verify_ssl: bool = True,
    ):
        """
        Initialize S3-compatible storage.

        Args:
            bucket_name: Name of the bucket/space
            provider: Service provider ('aws', 'digitalocean', 'minio', 'wasabi', etc.)
            endpoint_url: Custom endpoint URL (overrides provider default)
            region: Region/datacenter location
            access_key_id: Access key ID
            secret_access_key: Secret access key
            use_ssl: Whether to use HTTPS
            verify_ssl: Whether to verify SSL certificates
        """
        self.bucket_name = bucket_name or Config.AWS_S3_BUCKET_NAME
        if not self.bucket_name:
            msg = "bucket_name is required"
            raise ValueError(msg)

        self.provider = provider.lower()
        self.region = region or Config.AWS_REGION_NAME or "us-east-1"

        # Determine endpoint URL
        if endpoint_url:
            self.endpoint_url: str | None = endpoint_url
        elif self.provider in self.ENDPOINTS:
            endpoint_template = self.ENDPOINTS[self.provider]
            self.endpoint_url = (
                endpoint_template.format(region=self.region) if endpoint_template else None
            )
        else:
            msg = f"Unknown provider '{self.provider}'. Please specify endpoint_url."
            raise ValueError(msg)

        # Set up credentials
        self.access_key_id = access_key_id or Config.AWS_ACCESS_KEY_ID
        self.secret_access_key = secret_access_key or Config.AWS_SECRET_ACCESS_KEY

        if not self.access_key_id or not self.secret_access_key:
            msg = "Access key ID and secret access key are required"
            raise ValueError(msg)

        self.session = aioboto3.Session(
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name=self.region,
        )

        self.client_config: dict[str, Any] = {"use_ssl": use_ssl, "verify": verify_ssl}
        if self.endpoint_url:
            self.client_config["endpoint_url"] = self.endpoint_url

    def _client(self) -> Any:
        """Async context manager yielding an S3 client."""
        return self.session.client("s3", **self.client_config)

    @classmethod
    def for_digitalocean(
        cls, space_name: str, region: str, access_key: str, secret_key: str, **kwargs: Any
    ) -> "S3CompatibleStorage":
        """Convenience method for DigitalOcean Spaces."""
        return cls(
            bucket_name=space_name,
            provider="digitalocean",
            region=region,
            access_key_id=access_key,
            secret_access_key=secret_key,
            **kwargs,
        )

    @classmethod
    def for_minio(
        cls, bucket_name: str, endpoint_url: str, access_key: str, secret_key: str, **kwargs: Any
    ) -> "S3CompatibleStorage":
        """Convenience method for MinIO."""
        kwargs.setdefault("use_ssl", endpoint_url.startswith("https"))
        return cls(
            bucket_name=bucket_name,
            provider="minio",
            endpoint_url=endpoint_url,
            access_key_id=access_key,
            secret_access_key=secret_key,
            **kwargs,
        )

    @classmethod
    def for_wasabi(
        cls, bucket_name: str, region: str, access_key: str, secret_key: str, **kwargs: Any
    ) -> "S3CompatibleStorage":
        """Convenience method for Wasabi."""
        return cls(
            bucket_name=bucket_name,
            provider="wasabi",
            region=region,
            access_key_id=access_key,
            secret_access_key=secret_key,
            **kwargs,
        )

    @staticmethod
    def _folder_prefix(path: str) -> str:
        path = path.strip("/")
        return f"{path}/" if path else ""

    async def upload(
        self,
        file_path: str,
        content: bytes | BinaryIO,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if isinstance(content, (bytes, bytearray, memoryview)):
            body: BinaryIO = BytesIO(bytes(content))
        elif hasattr(content, "read"):
            body = content
        else:
            msg = "content must be bytes, bytearray, memoryview, or a file-like object"
            raise TypeError(msg)

        extra_args: dict[str, Any] = {
            "ContentType": content_type or self._get_content_type(file_path)
        }
        if metadata:
            extra_args["Metadata"] = {str(k): str(v) for k, v in metadata.items()}

        try:
            async with self._client() as s3:
                await s3.upload_fileobj(body, self.bucket_name, file_path, ExtraArgs=extra_args)
            return True
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 upload failed for %s: %s", file_path, e)
            return False

    async def download(self, file_path: str) -> bytes:
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self.bucket_name, Key=file_path)
                data = await response["Body"].read()
                return bytes(data)
        except ClientError as e:
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg) from e

    async def download_to_file(self, file_path: str, local_file_path: str) -> bool:
        """Download a file directly to a local file path (equivalent to boto3's download_file)."""
        try:
            async with self._client() as s3:
                await s3.download_file(self.bucket_name, file_path, local_file_path)
            return True
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 download_to_file failed for %s: %s", file_path, e)
            return False

    async def delete(self, file_path: str) -> bool:
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=file_path)
            return True
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 delete failed for %s: %s", file_path, e)
            return False

    async def exists(self, file_path: str) -> bool:
        try:
            async with self._client() as s3:
                await s3.head_object(Bucket=self.bucket_name, Key=file_path)
            return True
        except ClientError:
            return False

    async def size(self, file_path: str) -> int:
        try:
            async with self._client() as s3:
                response = await s3.head_object(Bucket=self.bucket_name, Key=file_path)
                return int(response["ContentLength"])
        except ClientError as e:
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg) from e

    async def list_files(self, path: str = "", recursive: bool = False) -> list[FileInfo]:
        prefix = self._folder_prefix(path)
        files: list[FileInfo] = []
        try:
            async with self._client() as s3:
                paginator = s3.get_paginator("list_objects_v2")
                kwargs: dict[str, Any] = {"Bucket": self.bucket_name, "Prefix": prefix}
                if not recursive:
                    kwargs["Delimiter"] = "/"
                async for page in paginator.paginate(**kwargs):
                    for obj in page.get("Contents", []):
                        key = obj.get("Key")
                        size = obj.get("Size")
                        last_modified = obj.get("LastModified")
                        # Skip folder placeholder objects and malformed entries
                        if not key or key.endswith("/") or size is None or last_modified is None:
                            continue
                        etag = obj.get("ETag")
                        files.append(
                            FileInfo(
                                name=key.rsplit("/", 1)[-1],
                                path=key,
                                size=size,
                                last_modified=last_modified,
                                content_type=self._get_content_type(key),
                                etag=etag.strip('"') if etag else None,
                            )
                        )
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 list_files failed for %s: %s", path, e)
            return []

        return sorted(files, key=lambda x: x.last_modified, reverse=True)

    async def list_folders(self, path: str = "") -> list[FolderInfo]:
        prefix = self._folder_prefix(path)
        folders: list[FolderInfo] = []
        try:
            async with self._client() as s3:
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(
                    Bucket=self.bucket_name, Prefix=prefix, Delimiter="/"
                ):
                    for prefix_obj in page.get("CommonPrefixes", []):
                        folder_prefix = prefix_obj.get("Prefix")
                        if not folder_prefix:
                            continue
                        folder_path = folder_prefix.rstrip("/")
                        folder_files = await self.list_files(folder_path, recursive=True)
                        folders.append(
                            FolderInfo(
                                name=folder_path.rsplit("/", 1)[-1],
                                path=folder_path,
                                file_count=len(folder_files),
                                total_size=sum(f.size for f in folder_files),
                                last_modified=max(
                                    (f.last_modified for f in folder_files),
                                    default=datetime.min.replace(tzinfo=UTC),
                                ),
                            )
                        )
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 list_folders failed for %s: %s", path, e)
            return []
        return folders

    async def get_file_info(self, file_path: str) -> FileInfo | None:
        try:
            async with self._client() as s3:
                response = await s3.head_object(Bucket=self.bucket_name, Key=file_path)
        except ClientError:
            return None
        etag = response.get("ETag")
        return FileInfo(
            name=file_path.rsplit("/", 1)[-1],
            path=file_path,
            size=int(response["ContentLength"]),
            last_modified=response["LastModified"],
            content_type=response.get("ContentType", "application/octet-stream"),
            etag=etag.strip('"') if etag else None,
            metadata=response.get("Metadata", {}),
        )

    async def create_folder(self, folder_path: str) -> bool:
        prefix = self._folder_prefix(folder_path)
        if not prefix:
            return False
        try:
            async with self._client() as s3:
                await s3.put_object(Bucket=self.bucket_name, Key=prefix)
            return True
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 create_folder failed for %s: %s", folder_path, e)
            return False

    async def delete_folder(self, folder_path: str, recursive: bool = False) -> bool:
        prefix = self._folder_prefix(folder_path)
        if not prefix:
            return False  # refuse to wipe the whole bucket
        try:
            keys: list[str] = []
            async with self._client() as s3:
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                    keys.extend(obj["Key"] for obj in page.get("Contents", []) if obj.get("Key"))

                real_files = [k for k in keys if not k.endswith("/")]
                if real_files and not recursive:
                    return False

                for i in range(0, len(keys), DELETE_BATCH_SIZE):
                    chunk = keys[i : i + DELETE_BATCH_SIZE]
                    await s3.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
                    )
            return True
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 delete_folder failed for %s: %s", folder_path, e)
            return False

    @staticmethod
    def _get_content_type(file_path: str) -> str:
        return mimetypes.guess_type(file_path)[0] or "application/octet-stream"
