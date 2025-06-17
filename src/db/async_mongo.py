import asyncio
import logging
from typing import Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from src.report.notify import async_report, NotificationType
from src.config import Config

# Configure logging
logger = logging.getLogger(__name__)

class MongoDBClient:
    def __init__(self, db_name: Optional[str] = None, max_pool_size: int = 10):
        self.mongo_uri = Config.MONGO_URI
        self.db_name = db_name or Config.MONGO_DB_NAME
        self.max_pool_size = max_pool_size
        self.client: AsyncIOMotorClient[Any] | None = None
        self.db = None
        self.collection: AsyncIOMotorCollection[Any] | None = None
        self._connection_lock = asyncio.Lock()
        
    async def connect(self):
        """Initialize async MongoDB connection"""
        async with self._connection_lock:
            if self.client is not None:
                return  # Already connected
            
            try:
                self.client = AsyncIOMotorClient(
                    self.mongo_uri,
                    maxPoolSize=self.max_pool_size,
                    minPoolSize=2,
                    maxIdleTimeMS=30000,
                    connectTimeoutMS=10000,
                    serverSelectionTimeoutMS=20000, # 20 seconds
                    retryWrites=True,
                    retryReads=True
                )
                
                # Test connection
                await asyncio.wait_for(
                    self.client.admin.command('ping'), 
                    timeout=5.0
                )
                logger.info("Connected to MongoDB successfully")
                
                self.db = self.client[self.db_name]
                # self.collection = self.db["your_collection_name"]  # Replace with your collection name
                
            except asyncio.TimeoutError:
                await async_report("MongoDB connection timed out", NotificationType.WARNING)
                await self.close()
                raise ConnectionError("MongoDB connection timeout")
            except Exception as e:
                await async_report(f"Failed to connect to MongoDB: {e}", NotificationType.ERROR)
                await self.close()
                raise
            
    async def ensure_connected(self):
        """Ensure connection is alive, reconnect if needed"""
        try:
            if not self.client:
                await self.connect()
                return
                
            # Ping to check if connection is alive
            await asyncio.wait_for(
                self.client.admin.command('ping'), 
                timeout=2.0
            )
        except Exception as e:
            await async_report(f"Connection check failed, reconnecting: {e}", NotificationType.WARNING)
            await self.close()
            await self.connect()
            
    def ensure_collection_exists(self):
        """Ensure the specified collection exists"""
        if not isinstance(self.collection, AsyncIOMotorCollection):
            raise ValueError("Collection is not set or not a valid AsyncIOMotorCollection instance")

    async def close(self):
        """Close the MongoDB connection"""
        if hasattr(self, 'client') and self.client is not None:
            self.client.close()
            logger.info("MongoDB connection closed")