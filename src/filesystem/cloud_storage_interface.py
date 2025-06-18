from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union, BinaryIO, Any
from datetime import datetime
from dataclasses import dataclass

@dataclass
class FileInfo:
    """Represents file information across all providers."""
    name: str
    path: str
    size: int
    last_modified: datetime
    content_type: str
    etag: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class FolderInfo:
    """Represents folder information."""
    name: str
    path: str
    file_count: int
    total_size: int
    last_modified: datetime


class CloudStorageInterface(ABC):
    """Abstract base class for cloud storage providers."""
    
    @abstractmethod
    async def upload(self, file_path: str, content: Union[bytes, BinaryIO], 
               content_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Upload a file to the storage."""
        pass
    
    @abstractmethod
    async def download(self, file_path: str) -> bytes:
        """Download a file from the storage."""
        pass
    
    @abstractmethod
    async def delete(self, file_path: str) -> bool:
        """Delete a file from the storage."""
        pass
    
    @abstractmethod
    async def exists(self, file_path: str) -> bool:
        """Check if a file exists."""
        pass
    
    @abstractmethod
    async def size(self, file_path: str) -> int:
        """Get file size in bytes."""
        pass
    
    @abstractmethod
    async def list_files(self, path: str = "", recursive: bool = False) -> List[FileInfo]:
        """List files in a directory."""
        pass
    
    @abstractmethod
    async def list_folders(self, path: str = "") -> List[FolderInfo]:
        """List folders in a directory."""
        pass
    
    @abstractmethod
    async def get_file_info(self, file_path: str) -> Optional[FileInfo]:
        """Get detailed file information."""
        pass
    
    @abstractmethod
    async def create_folder(self, folder_path: str) -> bool:
        """Create a folder/directory."""
        pass
    
    @abstractmethod
    async def delete_folder(self, folder_path: str, recursive: bool = False) -> bool:
        """Delete a folder/directory."""
        pass