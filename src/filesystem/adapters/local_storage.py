from typing import Dict, List, Optional, Union, BinaryIO, Any
from datetime import datetime
from pathlib import Path
import json
import mimetypes
import shutil
from src.filesystem.cloud_storage_interface import CloudStorageInterface, FileInfo, FolderInfo
from concurrent.futures import ThreadPoolExecutor
import asyncio
import aiofiles
import aiofiles.os

class LocalStorage(CloudStorageInterface):
    """Local filesystem storage implementation."""
    
    def __init__(self, base_path: str, max_workers: int = 10):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def _get_full_path(self, file_path: str) -> Path:
        return self.base_path / file_path
    
    async def upload(self, file_path: str, content: Union[bytes, BinaryIO], 
                    content_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        try:
            full_path = self._get_full_path(file_path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            if isinstance(content, (bytes, bytearray, memoryview)):
                async with aiofiles.open(full_path, 'wb') as f:
                    await f.write(content)
            else:
                # Handle BinaryIO
                data = content.read()
                if isinstance(data, bytes):
                    async with aiofiles.open(full_path, 'wb') as f:
                        await f.write(data)
                else:
                    if isinstance(data, str):
                        async with aiofiles.open(full_path, 'wb') as f:
                            await f.write(data.encode('utf-8'))
                    else:
                        raise TypeError(f"Cannot write data of type {type(data)} to binary file")
            
            # Store metadata if provided
            if metadata:
                metadata_path = full_path.with_suffix(full_path.suffix + '.meta')
                async with aiofiles.open(metadata_path, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(metadata))
            
            return True
        except Exception:
            return False
    
    async def download(self, file_path: str) -> bytes:
        full_path = self._get_full_path(file_path)
        if not await aiofiles.os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        async with aiofiles.open(full_path, 'rb') as f:
            return await f.read()
        
    async def download_to_file(self, file_path: str, local_file_path: str) -> bool:
        full_path = self._get_full_path(file_path)
        if not await aiofiles.os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            async with aiofiles.open(full_path, 'rb') as src_file:
                async with aiofiles.open(local_file_path, 'wb') as dest_file:
                    while True:
                        chunk = await src_file.read(1024 * 1024)  # Read in 1MB chunks
                        if not chunk:
                            break
                        await dest_file.write(chunk)
            return True
        except Exception:
            return False
    
    async def delete(self, file_path: str) -> bool:
        try:
            full_path = self._get_full_path(file_path)
            if await aiofiles.os.path.exists(full_path):
                await aiofiles.os.remove(full_path)
                # Also delete metadata file if exists
                metadata_path = full_path.with_suffix(full_path.suffix + '.meta')
                if await aiofiles.os.path.exists(metadata_path):
                    await aiofiles.os.remove(metadata_path)
                return True
            return False
        except Exception:
            return False
    
    async def exists(self, file_path: str) -> bool:
        return await aiofiles.os.path.exists(self._get_full_path(file_path))
    
    async def size(self, file_path: str) -> int:
        full_path = self._get_full_path(file_path)
        if not await aiofiles.os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        stat = await aiofiles.os.stat(full_path)
        return stat.st_size
    
    async def list_files(self, path: str = "", recursive: bool = False) -> List[FileInfo]:
        full_path = self._get_full_path(path)
        if not await aiofiles.os.path.exists(full_path):
            return []
        
        # Use thread pool for CPU-intensive file system operations
        def _list_files_sync():
            files: List[FileInfo] = []
            pattern = "**/*" if recursive else "*"
            
            for file_path_obj in full_path.glob(pattern):
                if file_path_obj.is_file() and not file_path_obj.name.endswith('.meta'):
                    relative_path = file_path_obj.relative_to(self.base_path)
                    stat = file_path_obj.stat()
                    
                    # Load metadata if exists
                    metadata_path = file_path_obj.with_suffix(file_path_obj.suffix + '.meta')
                    metadata: Dict[str, Any] = {}
                    if metadata_path.exists():
                        try:
                            with open(metadata_path, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                        except (json.JSONDecodeError, IOError):
                            pass
                    
                    files.append(FileInfo(
                        name=file_path_obj.name,
                        path=str(relative_path),
                        size=stat.st_size,
                        last_modified=datetime.fromtimestamp(stat.st_mtime),
                        content_type=mimetypes.guess_type(str(file_path_obj))[0] or 'application/octet-stream',
                        metadata=metadata
                    ))
            
            return sorted(files, key=lambda x: x.last_modified, reverse=True)
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _list_files_sync)
    
    async def list_folders(self, path: str = "") -> List[FolderInfo]:
        full_path = self._get_full_path(path)
        if not await aiofiles.os.path.exists(full_path):
            return []
        
        def _list_folders_sync():
            folders: List[FolderInfo] = []
            for folder_path_obj in full_path.iterdir():
                if folder_path_obj.is_dir():
                    relative_path = folder_path_obj.relative_to(self.base_path)
                    stat = folder_path_obj.stat()
                    
                    folders.append(FolderInfo(
                        name=folder_path_obj.name,
                        path=str(relative_path),
                        file_count=0,  # Will be computed separately for performance
                        total_size=0,  # Will be computed separately for performance
                        last_modified=datetime.fromtimestamp(stat.st_mtime)
                    ))
            return folders
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _list_folders_sync)
    
    async def get_file_info(self, file_path: str) -> Optional[FileInfo]:
        full_path = self._get_full_path(file_path)
        if not await aiofiles.os.path.exists(full_path):
            return None
        
        stat = await aiofiles.os.stat(full_path)
        
        # Load metadata if exists
        metadata_path = full_path.with_suffix(full_path.suffix + '.meta')
        metadata: Dict[str, Any] = {}
        if await aiofiles.os.path.exists(metadata_path):
            try:
                async with aiofiles.open(metadata_path, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    metadata = json.loads(content)
            except (json.JSONDecodeError, IOError):
                pass
        
        return FileInfo(
            name=full_path.name,
            path=file_path,
            size=stat.st_size,
            last_modified=datetime.fromtimestamp(stat.st_mtime),
            content_type=mimetypes.guess_type(str(full_path))[0] or 'application/octet-stream',
            metadata=metadata
        )
    
    async def create_folder(self, folder_path: str) -> bool:
        try:
            full_path = self._get_full_path(folder_path)
            await aiofiles.os.makedirs(full_path, exist_ok=True)
            return True
        except Exception:
            return False
    
    async def delete_folder(self, folder_path: str, recursive: bool = False) -> bool:
        try:
            full_path = self._get_full_path(folder_path)
            if not await aiofiles.os.path.exists(full_path):
                return False
            
            def _delete_folder_sync():
                if not recursive:
                    # Check if folder is empty
                    if any(full_path.iterdir()):
                        return False
                    full_path.rmdir()
                else:
                    shutil.rmtree(full_path)
                return True
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(self.executor, _delete_folder_sync)
        except Exception:
            return False
    
    # Batch operations for improved performance
    async def upload_batch(self, files: List[tuple[str, Union[bytes, BinaryIO], Optional[str], Optional[Dict[str, Any]]]]) -> List[bool]:
        """Upload multiple files concurrently."""
        tasks = [self.upload(file_path, content, content_type, metadata) 
                for file_path, content, content_type, metadata in files]
        return await asyncio.gather(*tasks, return_exceptions=False)
    
    async def download_batch(self, file_paths: List[str]) -> List[bytes]:
        """Download multiple files concurrently."""
        tasks = [self.download(file_path) for file_path in file_paths]
        return await asyncio.gather(*tasks)
    
    async def delete_batch(self, file_paths: List[str]) -> List[bool]:
        """Delete multiple files concurrently."""
        tasks = [self.delete(file_path) for file_path in file_paths]
        return await asyncio.gather(*tasks)