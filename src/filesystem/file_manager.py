import asyncio
import json
import logging
from typing import Any, BinaryIO

import aiofiles

from src.filesystem.cloud_storage_interface import (
    CloudStorageInterface,
    FileInfo,
    FolderInfo,
)
from src.filesystem.providers import StorageProvider

logger = logging.getLogger(__name__)

ProviderRef = StorageProvider | str | None


def _provider_key(provider: ProviderRef) -> str | None:
    if provider is None:
        return None
    return provider.value if isinstance(provider, StorageProvider) else provider


class FileManager:
    """
    Global file manager that maintains provider registry across instances.
    Uses a class-level registry to share providers between all instances, so
    `FileManager()` anywhere in the app sees what `boot.py` registered.
    """

    # Class-level storage for providers (shared across all instances)
    _providers: dict[str, CloudStorageInterface] = {}
    _default_provider: str | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def reset(cls) -> None:
        """Remove every provider. Useful for tests and re-booting."""
        async with cls._lock:
            cls._providers.clear()
            cls._default_provider = None

    async def add_provider(
        self, name: StorageProvider, provider: CloudStorageInterface, set_as_default: bool = False
    ) -> "FileManager":
        """
        Add a storage provider to the global registry.

        The first provider added becomes the default unless another one is
        explicitly registered with `set_as_default=True`.
        """
        async with self._lock:
            self.__class__._providers[name.value] = provider
            if set_as_default or self.__class__._default_provider is None:
                self.__class__._default_provider = name.value
        return self

    async def remove_provider(self, name: StorageProvider) -> bool:
        """Remove a provider from the registry."""
        async with self._lock:
            if name.value not in self._providers:
                return False
            del self.__class__._providers[name.value]
            if self.__class__._default_provider == name.value:
                self.__class__._default_provider = next(iter(self._providers), None)
            return True

    async def set_default_provider(self, name: StorageProvider) -> bool:
        """Set the default provider."""
        async with self._lock:
            if name.value in self._providers:
                self.__class__._default_provider = name.value
                return True
        return False

    def get_provider(self, name: ProviderRef = None) -> CloudStorageInterface:
        """
        Get a specific provider (enum or its string value) or the default provider.

        Raises:
            RuntimeError: If no providers are configured or provider not found
        """
        if not self._providers:
            msg = (
                "FileManager not initialized. Add providers first using add_provider() "
                "or configure in your application boot file."
            )
            raise RuntimeError(msg)

        key = _provider_key(name) or self._default_provider
        if key is None:
            msg = "No default provider set"
            raise RuntimeError(msg)

        if key not in self._providers:
            msg = f"Provider '{key}' not found. Available: {self.providers}"
            raise RuntimeError(msg)

        return self._providers[key]

    @property
    def providers(self) -> list[str]:
        """Get list of available provider names."""
        return list(self._providers.keys())

    @property
    def default_provider_name(self) -> str | None:
        """Get the name of the default provider."""
        return self._default_provider

    @property
    def is_initialized(self) -> bool:
        """Check if the file manager has at least one provider."""
        return bool(self._providers)

    # Convenience methods that use the default provider
    async def upload(
        self,
        file_path: str,
        content: bytes | BinaryIO,
        content_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        provider: ProviderRef = None,
    ) -> bool:
        """Upload a file using specified or default provider."""
        return await self.get_provider(provider).upload(file_path, content, content_type, metadata)

    async def upload_text(
        self,
        file_path: str,
        text: str,
        encoding: str = "utf-8",
        metadata: dict[str, Any] | None = None,
        provider: ProviderRef = None,
    ) -> bool:
        """Upload text content as a file."""
        content = text.encode(encoding)
        return await self.upload(
            file_path, content, f"text/plain; charset={encoding}", metadata, provider
        )

    async def upload_json(
        self,
        file_path: str,
        data: Any,
        metadata: dict[str, Any] | None = None,
        provider: ProviderRef = None,
    ) -> bool:
        """Upload JSON data as a file."""
        content = json.dumps(data, indent=2).encode("utf-8")
        return await self.upload(file_path, content, "application/json", metadata, provider)

    async def upload_file(
        self,
        file_path: str,
        local_file_path: str,
        metadata: dict[str, Any] | None = None,
        provider: ProviderRef = None,
    ) -> bool:
        """Upload a local file."""
        async with aiofiles.open(local_file_path, "rb") as f:
            content = await f.read()
        return await self.upload(file_path, content, metadata=metadata, provider=provider)

    async def download(self, file_path: str, provider: ProviderRef = None) -> bytes:
        """Download a file using specified or default provider."""
        return await self.get_provider(provider).download(file_path)

    async def download_text(
        self, file_path: str, encoding: str = "utf-8", provider: ProviderRef = None
    ) -> str:
        """Download and decode text content."""
        content = await self.download(file_path, provider)
        return content.decode(encoding)

    async def download_json(self, file_path: str, provider: ProviderRef = None) -> Any:
        """Download and parse JSON content."""
        return json.loads(await self.download_text(file_path, provider=provider))

    async def download_to_file(
        self, file_path: str, local_file_path: str, provider: ProviderRef = None
    ) -> None:
        """Download to a local file. Raises FileNotFoundError if the download fails."""
        success = await self.get_provider(provider).download_to_file(file_path, local_file_path)
        if not success:
            msg = f"Failed to download file: {file_path}"
            raise FileNotFoundError(msg)

    async def delete(self, file_path: str, provider: ProviderRef = None) -> bool:
        """Delete a file using specified or default provider."""
        return await self.get_provider(provider).delete(file_path)

    async def exists(self, file_path: str, provider: ProviderRef = None) -> bool:
        """Check if file exists using specified or default provider."""
        return await self.get_provider(provider).exists(file_path)

    async def size(self, file_path: str, provider: ProviderRef = None) -> int:
        """Get file size using specified or default provider."""
        return await self.get_provider(provider).size(file_path)

    async def list_files(
        self,
        path: str = "",
        recursive: bool = False,
        provider: ProviderRef = None,
        sort_by_date: bool = True,
    ) -> list[FileInfo]:
        """List files using specified or default provider."""
        files = await self.get_provider(provider).list_files(path, recursive)
        if sort_by_date:
            files.sort(key=lambda x: x.last_modified, reverse=True)
        return files

    async def list_folders(self, path: str = "", provider: ProviderRef = None) -> list[FolderInfo]:
        """List folders using specified or default provider."""
        return await self.get_provider(provider).list_folders(path)

    async def get_file_info(self, file_path: str, provider: ProviderRef = None) -> FileInfo | None:
        """Get file info using specified or default provider."""
        return await self.get_provider(provider).get_file_info(file_path)

    async def create_folder(self, folder_path: str, provider: ProviderRef = None) -> bool:
        """Create folder using specified or default provider."""
        return await self.get_provider(provider).create_folder(folder_path)

    async def delete_folder(
        self, folder_path: str, recursive: bool = False, provider: ProviderRef = None
    ) -> bool:
        """Delete folder using specified or default provider."""
        return await self.get_provider(provider).delete_folder(folder_path, recursive)

    async def copy(
        self,
        source_path: str,
        dest_path: str,
        source_provider: ProviderRef = None,
        dest_provider: ProviderRef = None,
    ) -> bool:
        """Copy a file between providers or within the same provider."""
        try:
            content, info = await asyncio.gather(
                self.download(source_path, source_provider),
                self.get_file_info(source_path, source_provider),
            )
            content_type = info.content_type if info else None
            metadata = info.metadata if info else None
            return await self.upload(
                dest_path, content, content_type, metadata=metadata, provider=dest_provider
            )
        except Exception as e:
            logger.error("Copy %s -> %s failed: %s", source_path, dest_path, e)
            return False

    async def move(
        self,
        source_path: str,
        dest_path: str,
        source_provider: ProviderRef = None,
        dest_provider: ProviderRef = None,
    ) -> bool:
        """Move a file between providers or within the same provider."""
        if await self.copy(source_path, dest_path, source_provider, dest_provider):
            return await self.delete(source_path, source_provider)
        return False

    async def upload_batch(
        self,
        uploads: list[tuple[str, bytes | BinaryIO, str | None, dict[str, Any] | None]],
        provider: ProviderRef = None,
    ) -> list[bool]:
        """Upload multiple files concurrently."""
        storage = self.get_provider(provider)
        return list(
            await asyncio.gather(
                *[storage.upload(fp, content, ct, meta) for fp, content, ct, meta in uploads]
            )
        )

    async def download_batch(
        self, file_paths: list[str], provider: ProviderRef = None
    ) -> list[bytes]:
        """Download multiple files concurrently."""
        storage = self.get_provider(provider)
        return list(await asyncio.gather(*[storage.download(fp) for fp in file_paths]))

    async def delete_batch(self, file_paths: list[str], provider: ProviderRef = None) -> list[bool]:
        """Delete multiple files concurrently."""
        storage = self.get_provider(provider)
        return list(await asyncio.gather(*[storage.delete(fp) for fp in file_paths]))

    async def exists_batch(self, file_paths: list[str], provider: ProviderRef = None) -> list[bool]:
        """Check existence of multiple files concurrently."""
        return list(await asyncio.gather(*[self.exists(fp, provider) for fp in file_paths]))

    async def get_file_info_batch(
        self, file_paths: list[str], provider: ProviderRef = None
    ) -> list[FileInfo | None]:
        """Get info for multiple files concurrently."""
        return list(await asyncio.gather(*[self.get_file_info(fp, provider) for fp in file_paths]))
