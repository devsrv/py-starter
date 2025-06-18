from typing import Dict, List, Optional, Union, BinaryIO, Any
from datetime import datetime
import mimetypes
from botocore.exceptions import ClientError
from src.config import Config
from src.filesystem.cloud_storage_interface import CloudStorageInterface, FileInfo, FolderInfo
from concurrent.futures import ThreadPoolExecutor
import aioboto3

class S3Storage(CloudStorageInterface):
    """Amazon S3 storage implementation."""
    
    def __init__(self, bucket_name: str|None = Config.AWS_S3_BUCKET_NAME, max_workers: int = 10):
        self.bucket_name = bucket_name or 'default-bucket'
        self.session = aioboto3.Session(
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            region_name=Config.AWS_REGION_NAME
        )
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    async def upload(self, file_path: str, content: Union[bytes, BinaryIO], 
                    content_type: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        try:
            if content_type is None:
                content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
            
            extra_args: Dict[str, Any] = {'ContentType': content_type}
            if metadata:
                extra_args['Metadata'] = {str(k): str(v) for k, v in metadata.items()}
            
            from io import BytesIO
            if isinstance(content, (bytes, bytearray, memoryview)):
                content = BytesIO(content)
            elif not hasattr(content, "read"):
                raise TypeError("content must be bytes, bytearray, memoryview, or a file-like object")
            
            async with self.session.client('s3') as s3:
                await s3.upload_fileobj(content, self.bucket_name, file_path, ExtraArgs=extra_args)
            return True
        except ClientError:
            return False
    
    async def download(self, file_path: str) -> bytes:
        try:
            async with self.session.client('s3') as s3:
                response = await s3.get_object(Bucket=self.bucket_name, Key=file_path)
                body = response['Body']
                return await body.read()
        except ClientError as e:
            raise FileNotFoundError(f"File not found: {file_path}")
    
    async def delete(self, file_path: str) -> bool:
        try:
            async with self.session.client('s3') as s3:
                await s3.delete_object(Bucket=self.bucket_name, Key=file_path)
            return True
        except ClientError:
            return False
    
    async def exists(self, file_path: str) -> bool:
        try:
            async with self.session.client('s3') as s3:
                await s3.head_object(Bucket=self.bucket_name, Key=file_path)
            return True
        except ClientError:
            return False
    
    async def size(self, file_path: str) -> int:
        try:
            async with self.session.client('s3') as s3:
                response = await s3.head_object(Bucket=self.bucket_name, Key=file_path)
                return response['ContentLength']
        except ClientError:
            raise FileNotFoundError(f"File not found: {file_path}")
    
    async def list_files(self, path: str = "", recursive: bool = False) -> List[FileInfo]:
        try:
            if path and not path.endswith('/'):
                path += '/'
            
            delimiter = '' if recursive else '/'
            files: List[FileInfo] = []
            
            async with self.session.client('s3') as s3:
                paginator = s3.get_paginator('list_objects_v2')
                async for page in paginator.paginate(
                    Bucket=self.bucket_name,
                    Prefix=path,
                    Delimiter=delimiter
                ):
                    contents = page.get('Contents', [])
                    for obj in contents:
                        obj_key = obj.get('Key')
                        obj_size = obj.get('Size')
                        obj_last_modified = obj.get('LastModified')
                        obj_etag = obj.get('ETag')
                        
                        # Skip if required fields are missing or if it's the folder itself
                        if not obj_key or obj_key == path or obj_size is None or obj_last_modified is None:
                            continue
                        
                        files.append(FileInfo(
                            name=obj_key.split('/')[-1],
                            path=obj_key,
                            size=obj_size,
                            last_modified=obj_last_modified,
                            content_type=self._get_content_type(obj_key),
                            etag=obj_etag.strip('"') if obj_etag else ""
                        ))
            
            return sorted(files, key=lambda x: x.last_modified, reverse=True)
        except ClientError:
            return []
    
    async def list_folders(self, path: str = "") -> List[FolderInfo]:
        try:
            if path and not path.endswith('/'):
                path += '/'
            
            folders: List[FolderInfo] = []
            
            async with self.session.client('s3') as s3:
                response = await s3.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=path,
                    Delimiter='/'
                )
                
                common_prefixes = response.get('CommonPrefixes', [])
                
                for prefix_obj in common_prefixes:
                    prefix = prefix_obj.get('Prefix')
                    if not prefix:
                        continue
                        
                    folder_path = prefix.rstrip('/')
                    folder_name = folder_path.split('/')[-1]
                    
                    # Get folder stats
                    folder_files = await self.list_files(folder_path, recursive=True)
                    file_count = len(folder_files)
                    total_size = sum(f.size for f in folder_files)
                    last_modified = max((f.last_modified for f in folder_files), default=datetime.min)
                    
                    folders.append(FolderInfo(
                        name=folder_name,
                        path=folder_path,
                        file_count=file_count,
                        total_size=total_size,
                        last_modified=last_modified
                    ))
            
            return folders
        except ClientError:
            return []
    
    async def get_file_info(self, file_path: str) -> Optional[FileInfo]:
        try:
            async with self.session.client('s3') as s3:
                response = await s3.head_object(Bucket=self.bucket_name, Key=file_path)
                return FileInfo(
                    name=file_path.split('/')[-1],
                    path=file_path,
                    size=response['ContentLength'],
                    last_modified=response['LastModified'],
                    content_type=response.get('ContentType', 'application/octet-stream'),
                    etag=response['ETag'].strip('"'),
                    metadata=response.get('Metadata', {})
                )
        except ClientError:
            return None
    
    async def create_folder(self, folder_path: str) -> bool:
        try:
            if not folder_path.endswith('/'):
                folder_path += '/'
            async with self.session.client('s3') as s3:
                await s3.put_object(Bucket=self.bucket_name, Key=folder_path)
            return True
        except ClientError:
            return False
    
    async def delete_folder(self, folder_path: str, recursive: bool = False) -> bool:
        try:
            if not recursive:
                # Check if folder is empty
                files = await self.list_files(folder_path)
                if files:
                    return False
            
            # Delete all files in folder
            if not folder_path.endswith('/'):
                folder_path += '/'
            
            objects_to_delete = []
            async with self.session.client('s3') as s3:
                paginator = s3.get_paginator('list_objects_v2')
                async for page in paginator.paginate(Bucket=self.bucket_name, Prefix=folder_path):
                    contents = page.get('Contents', [])
                    for obj in contents:
                        obj_key = obj.get('Key')
                        if obj_key:
                            objects_to_delete.append({'Key': obj_key})
                
                if objects_to_delete:
                    await s3.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={'Objects': objects_to_delete}
                    )
            
            return True
        except ClientError:
            return False
    
    def _get_content_type(self, file_path: str) -> str:
        return mimetypes.guess_type(file_path)[0] or 'application/octet-stream'