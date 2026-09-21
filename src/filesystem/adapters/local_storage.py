import asyncio
import json
import logging
import mimetypes
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

import aiofiles
import aiofiles.os

from src.filesystem.cloud_storage_interface import (
    CloudStorageInterface,
    FileInfo,
    FolderInfo,
)

logger = logging.getLogger(__name__)

META_SUFFIX = ".meta"


class LocalStorage(CloudStorageInterface):
    """Local filesystem storage implementation.

    Files live under `base_path`. Metadata passed to `upload()` is kept in a
    sidecar `<file>.meta` JSON file next to the file. Paths that try to escape
    `base_path` (e.g. `../../etc/passwd`) are rejected with ValueError.
    """

    def __init__(self, base_path: str, max_workers: int = 10):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def _get_full_path(self, file_path: str) -> Path:
        candidate = (self.base_path / file_path.lstrip("/")).resolve()
        if candidate != self.base_path and self.base_path not in candidate.parents:
            msg = f"Path escapes storage root: {file_path!r}"
            raise ValueError(msg)
        return candidate

    @staticmethod
    def _meta_path(full_path: Path) -> Path:
        return full_path.with_name(full_path.name + META_SUFFIX)

    @staticmethod
    def _mtime(stat: Any) -> datetime:
        return datetime.fromtimestamp(stat.st_mtime, tz=UTC)

    @staticmethod
    def _content_type(path: Path) -> str:
        return mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    def _read_meta_sync(self, full_path: Path) -> dict[str, Any]:
        meta_path = self._meta_path(full_path)
        if not meta_path.exists():
            return {}
        try:
            loaded = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}

    async def upload(
        self,
        file_path: str,
        content: bytes | BinaryIO,
        content_type: str | None = None,  # noqa: ARG002 - not stored on local disk
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        try:
            full_path = self._get_full_path(file_path)
            full_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, (bytes, bytearray, memoryview)):
                data: bytes = bytes(content)
            elif hasattr(content, "read"):
                raw = content.read()
                if isinstance(raw, str):
                    raw = raw.encode("utf-8")
                if not isinstance(raw, (bytes, bytearray, memoryview)):
                    msg = f"Cannot write data of type {type(raw)} to binary file"
                    raise TypeError(msg)
                data = bytes(raw)
            else:
                msg = "content must be bytes or a file-like object"
                raise TypeError(msg)

            async with aiofiles.open(full_path, "wb") as f:
                await f.write(data)

            meta_path = self._meta_path(full_path)
            if metadata:
                async with aiofiles.open(meta_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(metadata))
            elif await aiofiles.os.path.exists(meta_path):
                # Overwriting a file without metadata should not keep stale metadata
                await aiofiles.os.remove(meta_path)

            return True
        except Exception as e:
            logger.error("Local upload failed for %s: %s", file_path, e)
            return False

    async def download(self, file_path: str) -> bytes:
        full_path = self._get_full_path(file_path)
        if not await aiofiles.os.path.isfile(full_path):
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()

    async def download_to_file(self, file_path: str, local_file_path: str) -> bool:
        full_path = self._get_full_path(file_path)
        if not await aiofiles.os.path.isfile(full_path):
            return False

        try:
            Path(local_file_path).parent.mkdir(parents=True, exist_ok=True)
            async with (
                aiofiles.open(full_path, "rb") as src_file,
                aiofiles.open(local_file_path, "wb") as dest_file,
            ):
                while chunk := await src_file.read(1024 * 1024):  # 1MB chunks
                    await dest_file.write(chunk)
            return True
        except Exception as e:
            logger.error("Local download_to_file failed for %s: %s", file_path, e)
            return False

    async def delete(self, file_path: str) -> bool:
        try:
            full_path = self._get_full_path(file_path)
            if not await aiofiles.os.path.isfile(full_path):
                return False
            await aiofiles.os.remove(full_path)
            meta_path = self._meta_path(full_path)
            if await aiofiles.os.path.exists(meta_path):
                await aiofiles.os.remove(meta_path)
            return True
        except Exception as e:
            logger.error("Local delete failed for %s: %s", file_path, e)
            return False

    async def exists(self, file_path: str) -> bool:
        try:
            return await aiofiles.os.path.isfile(self._get_full_path(file_path))
        except ValueError:
            return False

    async def size(self, file_path: str) -> int:
        full_path = self._get_full_path(file_path)
        if not await aiofiles.os.path.isfile(full_path):
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)
        stat = await aiofiles.os.stat(full_path)
        return stat.st_size

    async def list_files(self, path: str = "", recursive: bool = False) -> list[FileInfo]:
        full_path = self._get_full_path(path)
        if not await aiofiles.os.path.isdir(full_path):
            return []

        def _list_files_sync() -> list[FileInfo]:
            files: list[FileInfo] = []
            pattern = "**/*" if recursive else "*"

            for p in full_path.glob(pattern):
                if not p.is_file() or p.name.endswith(META_SUFFIX):
                    continue
                stat = p.stat()
                files.append(
                    FileInfo(
                        name=p.name,
                        path=p.relative_to(self.base_path).as_posix(),
                        size=stat.st_size,
                        last_modified=self._mtime(stat),
                        content_type=self._content_type(p),
                        metadata=self._read_meta_sync(p),
                    )
                )

            return sorted(files, key=lambda x: x.last_modified, reverse=True)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, _list_files_sync)

    async def list_folders(self, path: str = "") -> list[FolderInfo]:
        full_path = self._get_full_path(path)
        if not await aiofiles.os.path.isdir(full_path):
            return []

        def _list_folders_sync() -> list[FolderInfo]:
            folders: list[FolderInfo] = []
            for p in full_path.iterdir():
                if not p.is_dir():
                    continue
                files = [
                    f for f in p.rglob("*") if f.is_file() and not f.name.endswith(META_SUFFIX)
                ]
                folders.append(
                    FolderInfo(
                        name=p.name,
                        path=p.relative_to(self.base_path).as_posix(),
                        file_count=len(files),
                        total_size=sum(f.stat().st_size for f in files),
                        last_modified=self._mtime(p.stat()),
                    )
                )
            return sorted(folders, key=lambda x: x.name)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, _list_folders_sync)

    async def get_file_info(self, file_path: str) -> FileInfo | None:
        full_path = self._get_full_path(file_path)
        if not await aiofiles.os.path.isfile(full_path):
            return None

        stat = await aiofiles.os.stat(full_path)
        return FileInfo(
            name=full_path.name,
            path=full_path.relative_to(self.base_path).as_posix(),
            size=stat.st_size,
            last_modified=self._mtime(stat),
            content_type=self._content_type(full_path),
            metadata=self._read_meta_sync(full_path),
        )

    async def create_folder(self, folder_path: str) -> bool:
        try:
            full_path = self._get_full_path(folder_path)
            await aiofiles.os.makedirs(full_path, exist_ok=True)
            return True
        except Exception as e:
            logger.error("Local create_folder failed for %s: %s", folder_path, e)
            return False

    async def delete_folder(self, folder_path: str, recursive: bool = False) -> bool:
        try:
            full_path = self._get_full_path(folder_path)
            if full_path == self.base_path:
                return False  # never delete the storage root itself
            if not await aiofiles.os.path.isdir(full_path):
                return False

            def _delete_folder_sync() -> bool:
                if recursive:
                    shutil.rmtree(full_path)
                    return True
                if any(full_path.iterdir()):
                    return False
                full_path.rmdir()
                return True

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self.executor, _delete_folder_sync)
        except Exception as e:
            logger.error("Local delete_folder failed for %s: %s", folder_path, e)
            return False

    # Batch operations for improved performance
    async def upload_batch(
        self,
        files: list[tuple[str, bytes | BinaryIO, str | None, dict[str, Any] | None]],
    ) -> list[bool]:
        """Upload multiple files concurrently."""
        return list(
            await asyncio.gather(
                *[self.upload(fp, content, ct, meta) for fp, content, ct, meta in files]
            )
        )

    async def download_batch(self, file_paths: list[str]) -> list[bytes]:
        """Download multiple files concurrently."""
        return list(await asyncio.gather(*[self.download(fp) for fp in file_paths]))

    async def delete_batch(self, file_paths: list[str]) -> list[bool]:
        """Delete multiple files concurrently."""
        return list(await asyncio.gather(*[self.delete(fp) for fp in file_paths]))
