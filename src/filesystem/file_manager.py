from typing import Dict, List, Optional, Union, BinaryIO, Any
from src.filesystem.cloud_storage_interface import CloudStorageInterface, FileInfo, FolderInfo
from enum import Enum
import asyncio

class StorageProvider(Enum):
    """Supported storage providers."""
    LOCAL = "local"
    S3 = "s3"
    # Add more providers as needed, e.g., AZURE, S3_BACKUP etc.

class FileManager:
    """
    Global file manager that maintains provider registry across instances.
    Uses a class-level registry to share providers between all instances.
    """
    
    # Class-level storage for providers (shared across all instances)
    _providers: Dict[str, CloudStorageInterface] = {}
    _default_provider: Optional[str] = None
    _initialized: bool = False
    _lock = asyncio.Lock()
    
    def __init__(self):
        # All instances share the same provider registry
        pass
    
    @classmethod
    async def reset(cls) -> None:
        """Reset all providers and configuration. Useful for testing."""
        async with cls._lock:
            cls._providers.clear()
            cls._default_provider = None
            cls._initialized = False
    
    async def add_provider(self, name: StorageProvider, provider: CloudStorageInterface, 
                    set_as_default: bool = False) -> 'FileManager':
        """
        Add a storage provider to the global registry.
        
        Args:
            name: Unique name for the provider (e.g., 'local', 's3', 'backup-s3')
            provider: Storage provider instance
            set_as_default: Whether to set this as the default provider
            
        Returns:
            Self for method chaining
        """
        async with self.__class__._lock:
            self.__class__._providers[name.value] = provider
            
            if set_as_default or self.__class__._default_provider is None:
                self.__class__._default_provider = name.value
                
            self.__class__._initialized = True
        return self
    
    async def remove_provider(self, name: StorageProvider) -> bool:
        """Remove a provider from the registry."""
        async with self.__class__._lock:
            if name.value in self.__class__._providers:
                del self.__class__._providers[name.value]
                
                # If we removed the default provider, set a new one
                if self.__class__._default_provider == name.value:
                    if self.__class__._providers:
                        self.__class__._default_provider = next(iter(self.__class__._providers))
                    else:
                        self.__class__._default_provider = None
                        self.__class__._initialized = False
                return True
        return False
    
    async def set_default_provider(self, name: StorageProvider) -> bool:
        """Set the default provider."""
        async with self.__class__._lock:
            if name.value in self.__class__._providers:
                self.__class__._default_provider = name.value
                return True
        return False
    
    def get_provider(self, name: Optional[str] = None) -> CloudStorageInterface:
        """
        Get a specific provider or the default provider.
        
        Args:
            name: Provider name. If None, uses default provider.
            
        Returns:
            Storage provider instance
            
        Raises:
            RuntimeError: If no providers are configured or provider not found
        """
        if not self.__class__._initialized:
            raise RuntimeError(
                "FileManager not initialized. Add providers first using add_provider() "
                "or configure in your application boot file."
            )
        
        if name is None:
            name = self.__class__._default_provider
            
        if name is None:
            raise RuntimeError("No default provider set")
            
        if name not in self.__class__._providers:
            available = list(self.__class__._providers.keys())
            raise RuntimeError(f"Provider '{name}' not found. Available: {available}")
            
        return self.__class__._providers[name]
    
    @property
    def providers(self) -> List[str]:
        """Get list of available provider names."""
        return list(self.__class__._providers.keys())
    
    @property
    def default_provider_name(self) -> Optional[str]:
        """Get the name of the default provider."""
        return self.__class__._default_provider
    
    @property
    def is_initialized(self) -> bool:
        """Check if the file manager has been initialized with providers."""
        return self.__class__._initialized
    
    # Convenience methods that use the default provider
    async def upload(self, file_path: str, content: Union[bytes, BinaryIO], 
               content_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None,
               provider: Optional[StorageProvider] = None) -> bool:
        """Upload a file using specified or default provider."""
        return await self.get_provider(provider.value if provider else None).upload(file_path, content, content_type, metadata)
    
    async def upload_text(self, file_path: str, text: str, encoding: str = 'utf-8', 
                   metadata: Optional[Dict[str, Any]] = None, provider: Optional[StorageProvider] = None) -> bool:
        """Upload text content as a file."""
        content = text.encode(encoding)
        content_type = 'text/plain; charset=' + encoding
        return await self.upload(file_path, content, content_type, metadata, provider)
    
    async def upload_json(self, file_path: str, data: Any, 
                   metadata: Optional[Dict[str, Any]] = None, provider: Optional[StorageProvider] = None) -> bool:
        """Upload JSON data as a file."""
        import json
        content = json.dumps(data, indent=2).encode('utf-8')
        return await self.upload(file_path, content, 'application/json', metadata, provider)
    
    async def upload_file(self, file_path: str, local_file_path: str, 
                   metadata: Optional[Dict[str, Any]] = None, provider: Optional[StorageProvider] = None) -> bool:
        """Upload a local file."""
        with open(local_file_path, 'rb') as f:
            return await self.upload(file_path, f, metadata=metadata, provider=provider)
    
    async def download(self, file_path: str, provider: Optional[StorageProvider] = None) -> bytes:
        """Download a file using specified or default provider."""
        return await self.get_provider(provider.value if provider else None).download(file_path)
    
    async def download_text(self, file_path: str, encoding: str = 'utf-8', 
                     provider: Optional[StorageProvider] = None) -> str:
        """Download and decode text content."""
        content = await self.download(file_path, provider)
        return content.decode(encoding)
    
    async def download_json(self, file_path: str, provider: Optional[StorageProvider] = None) -> Any:
        """Download and parse JSON content."""
        import json
        content = await self.download_text(file_path, provider=provider)
        return json.loads(content)
    
    async def download_to_file(self, file_path: str, local_file_path: str, 
                        provider: Optional[StorageProvider] = None) -> None:
        """Download to a local file."""
        content = await self.download(file_path, provider)
        with open(local_file_path, 'wb') as f:
            f.write(content)
    
    async def delete(self, file_path: str, provider: Optional[StorageProvider] = None) -> bool:
        """Delete a file using specified or default provider."""
        return await self.get_provider(provider.value if provider else None).delete(file_path)
    
    async def exists(self, file_path: str, provider: Optional[StorageProvider] = None) -> bool:
        """Check if file exists using specified or default provider."""
        return await self.get_provider(provider.value if provider else None).exists(file_path)
    
    async def size(self, file_path: str, provider: Optional[StorageProvider] = None) -> int:
        """Get file size using specified or default provider."""
        return await self.get_provider(provider.value if provider else None).size(file_path)
    
    async def list_files(self, path: str = "", recursive: bool = False, 
                   provider: Optional[StorageProvider] = None, sort_by_date: bool = True) -> List[FileInfo]:
        """List files using specified or default provider."""
        files = await self.get_provider(provider.value if provider else None).list_files(path, recursive)
        if sort_by_date:
            files.sort(key=lambda x: x.last_modified, reverse=True)
        return files
    
    async def list_folders(self, path: str = "", provider: Optional[StorageProvider] = None) -> List[FolderInfo]:
        """List folders using specified or default provider."""
        return await self.get_provider(provider.value if provider else None).list_folders(path)
    
    async def get_file_info(self, file_path: str, provider: Optional[StorageProvider] = None) -> Optional[FileInfo]:
        """Get file info using specified or default provider."""
        return await self.get_provider(provider.value if provider else None).get_file_info(file_path)
    
    async def create_folder(self, folder_path: str, provider: Optional[StorageProvider] = None) -> bool:
        """Create folder using specified or default provider."""
        return await self.get_provider(provider.value if provider else None).create_folder(folder_path)
    
    async def delete_folder(self, folder_path: str, recursive: bool = False, 
                     provider: Optional[StorageProvider] = None) -> bool:
        """Delete folder using specified or default provider."""
        return await self.get_provider(provider.value if provider else None).delete_folder(folder_path, recursive)
    
    async def copy(self, source_path: str, dest_path: str, 
                  source_provider: Optional[StorageProvider] = None, 
                  dest_provider: Optional[StorageProvider] = None) -> bool:
        """Copy a file between providers or within the same provider."""
        try:
            # Download and upload concurrently if different providers
            content_task = self.download(source_path, source_provider)
            info_task = self.get_file_info(source_path, source_provider)
            
            content, info = await asyncio.gather(content_task, info_task)
            metadata = info.metadata if info else None
            
            return await self.upload(dest_path, content, metadata=metadata, provider=dest_provider)
        except Exception:
            return False
    
    async def move(self, source_path: str, dest_path: str, 
                  source_provider: Optional[StorageProvider] = None, 
                  dest_provider: Optional[StorageProvider] = None) -> bool:
        """Move a file between providers or within the same provider."""
        if await self.copy(source_path, dest_path, source_provider, dest_provider):
            return await self.delete(source_path, source_provider)
        return False
    
    async def upload_batch(self, uploads: List[tuple[str, Union[bytes, BinaryIO], Optional[str], Optional[Dict[str, Any]]]],
                          provider: Optional[StorageProvider] = None) -> List[bool]:
        """Upload multiple files concurrently."""
        storage_provider = self.get_provider(provider.value if provider else None)
        tasks = [storage_provider.upload(file_path, content, content_type, metadata) 
                 for file_path, content, content_type, metadata in uploads]
        return await asyncio.gather(*tasks)
    
    async def download_batch(self, file_paths: List[str], 
                            provider: Optional[StorageProvider] = None) -> List[bytes]:
        """Download multiple files concurrently."""
        storage_provider = self.get_provider(provider.value if provider else None)
        tasks = [storage_provider.download(file_path) for file_path in file_paths]
        return await asyncio.gather(*tasks)
    
    async def delete_batch(self, file_paths: List[str], 
                          provider: Optional[StorageProvider] = None) -> List[bool]:
        """Delete multiple files concurrently."""
        storage_provider = self.get_provider(provider.value if provider else None)
        tasks = [storage_provider.delete(file_path) for file_path in file_paths]
        return await asyncio.gather(*tasks)
    
    async def exists_batch(self, file_paths: List[str], 
                          provider: Optional[StorageProvider] = None) -> List[bool]:
        """Check existence of multiple files concurrently."""
        tasks = [self.exists(path, provider) for path in file_paths]
        return await asyncio.gather(*tasks)
    
    async def get_file_info_batch(self, file_paths: List[str], 
                                 provider: Optional[StorageProvider] = None) -> List[Optional[FileInfo]]:
        """Get info for multiple files concurrently."""
        tasks = [self.get_file_info(path, provider) for path in file_paths]
        return await asyncio.gather(*tasks)