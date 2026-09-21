from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, BinaryIO


@dataclass
class FileInfo:
    """Represents file information across all providers."""

    name: str
    path: str
    size: int
    last_modified: datetime
    content_type: str
    etag: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class FolderInfo:
    """Represents folder information."""

    name: str
    path: str
    file_count: int
    total_size: int
    last_modified: datetime


class CloudStorageInterface(ABC):
    """Abstract base class for storage providers (local disk, S3, Spaces, MinIO...)."""

    @abstractmethod
    async def upload(
        self,
        file_path: str,
        content: bytes | BinaryIO,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Upload a file to the storage."""

    @abstractmethod
    async def download_to_file(self, file_path: str, local_file_path: str) -> bool:
        """Download a file directly to a local file path."""

    @abstractmethod
    async def download(self, file_path: str) -> bytes:
        """Download a file from the storage. Raises FileNotFoundError if missing."""

    @abstractmethod
    async def delete(self, file_path: str) -> bool:
        """Delete a file from the storage."""

    @abstractmethod
    async def exists(self, file_path: str) -> bool:
        """Check if a file exists."""

    @abstractmethod
    async def size(self, file_path: str) -> int:
        """Get file size in bytes. Raises FileNotFoundError if missing."""

    @abstractmethod
    async def list_files(self, path: str = "", recursive: bool = False) -> list[FileInfo]:
        """List files in a directory."""

    @abstractmethod
    async def list_folders(self, path: str = "") -> list[FolderInfo]:
        """List folders in a directory."""

    @abstractmethod
    async def get_file_info(self, file_path: str) -> FileInfo | None:
        """Get detailed file information."""

    @abstractmethod
    async def create_folder(self, folder_path: str) -> bool:
        """Create a folder/directory."""

    @abstractmethod
    async def delete_folder(self, folder_path: str, recursive: bool = False) -> bool:
        """Delete a folder/directory."""
