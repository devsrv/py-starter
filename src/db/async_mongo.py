import asyncio
import logging
from typing import Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from src.report.notify import async_report, NotificationType
from src.config import Config
import backoff

# Configure logging
logger = logging.getLogger(__name__)


class MongoDBManager:
    """Singleton MongoDB manager for async operations"""
    _instance: Optional['MongoDBManager'] = None
    _initialized: bool = False
    _lock = asyncio.Lock()
    
    def __new__(cls) -> 'MongoDBManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Only initialize once
        if not hasattr(self, '_attrs_set'):
            self.mongo_uri = Config.MONGO_URI
            self.db_name = Config.MONGO_DB_NAME
            self.max_pool_size = 10
            self.client: Optional[AsyncIOMotorClient[Any]] = None
            self.db: Optional[AsyncIOMotorDatabase[Any]] = None
            self._connection_lock = asyncio.Lock()
            self._attrs_set = True
        
    async def initialize(self, db_name: Optional[str]=None, max_pool_size: int=10) -> None:
        """Initialize the MongoDB connection (call once at app startup)"""
        async with self._lock:
            if self._initialized:
                logger.info("MongoDB manager already initialized")
                return
            
            # Override defaults if provided
            if db_name:
                self.db_name = db_name
            self.max_pool_size = max_pool_size
            
            await self._connect()
            self._initialized = True
    
    async def _connect(self) -> None:
        """Internal method to establish MongoDB connection"""
        try:
            self.client = AsyncIOMotorClient(
                self.mongo_uri,
                maxPoolSize=self.max_pool_size,
                minPoolSize=2,
                maxIdleTimeMS=30000,
                connectTimeoutMS=10000,
                serverSelectionTimeoutMS=20000,
                retryWrites=True,
                retryReads=True,
                # w='majority',  # Write concern for durability
                # readPreference='primaryPreferred'
            )
            
            # Test connection
            await self._ping_with_retry()
            logger.info("Connected to MongoDB successfully")
            
            self.db = self.client[self.db_name]
            
        except asyncio.TimeoutError:
            await async_report("MongoDB connection timed out", NotificationType.WARNING)
            await self._cleanup()
            raise ConnectionError("MongoDB connection timeout")
        except Exception as e:
            await async_report(f"Failed to connect to MongoDB: {e}", NotificationType.ERROR)
            await self._cleanup()
            raise
        
    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        max_time=10
    )
    async def _ping_with_retry(self):
        if not self.client:
            raise RuntimeError("MongoDB client not initialized")
        
        """Ping MongoDB with exponential backoff retry"""
        await asyncio.wait_for(
            self.client.admin.command('ping'),
            timeout=5.0
        )
            
    async def ensure_connected(self) -> None:
        """Ensure connection is alive, reconnect if needed"""
        if not self._initialized:
            raise RuntimeError("MongoDB manager not initialized. Call initialize() first.")
        
        try:
            if not self.client:
                await self._connect()
                return
                
            # Ping to check if connection is alive
            await asyncio.wait_for(
                self.client.admin.command('ping'),
                timeout=2.0
            )
        except Exception as e:
            await async_report(f"Connection check failed, reconnecting: {e}", NotificationType.WARNING)
            await self._cleanup()
            await self._connect()
    
    def get_collection(self, collection_name: str) -> AsyncIOMotorCollection[Any]:
        """Get a collection from the database"""
        if self.db is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.db[collection_name]
    
    def get_database(self, db_name: Optional[str]=None) -> AsyncIOMotorDatabase[Any]:
        """Get database instance (current or specified)"""
        if self.client is None:
            raise RuntimeError("Client not initialized. Call initialize() first.")
        
        if db_name:
            return self.client[db_name]
        
        if self.db is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.db
    
    async def _cleanup(self) -> None:
        """Internal cleanup method"""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
    
    async def close(self) -> None:
        """Close the MongoDB connection (call at app shutdown)"""
        async with self._lock:
            if self.client:
                self.client.close()
                logger.info("MongoDB connection closed")
                self.client = None
                self.db = None
                self._initialized = False
    
    # Health check method
    async def health_check(self) -> dict[str, Any]:
        """Perform health check on MongoDB connection"""
        try:
            await self.ensure_connected()
            if self.db is None:
                raise RuntimeError("Database not initialized after connection attempt")
            stats = await self.db.command("dbStats")
            return {
                "status": "healthy",
                "database": self.db_name,
                "collections": stats.get("collections", 0),
                "dataSize": stats.get("dataSize", 0)
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }


# Global singleton instance
mongo_manager = MongoDBManager()


# Convenience functions for easier usage
async def get_collection(collection_name: str) -> AsyncIOMotorCollection[Any]:
    """Get a collection from the default database"""
    await mongo_manager.ensure_connected()
    return mongo_manager.get_collection(collection_name)


async def get_database(db_name: Optional[str]=None) -> AsyncIOMotorDatabase[Any]:
    """Get database instance"""
    await mongo_manager.ensure_connected()
    return mongo_manager.get_database(db_name)

# Usage examples : -

# # 1. In your main application startup (e.g., FastAPI, Django, etc.)
# async def startup():
#     await mongo_manager.initialize()
#     # or with custom settings:
#     # await mongo_manager.initialize(db_name="custom_db", max_pool_size=20)

# # 2. In your application shutdown
# async def shutdown():
#     await mongo_manager.close()

# # 3. In any service/module - no need to pass client around
# from path.to.this.file import mongo_manager, get_collection

# class UserService:
#     async def get_user(self, user_id: str):
#         users_collection = await get_collection("users")
#         return await users_collection.find_one({"_id": user_id})
    
#     async def create_user(self, user_data: dict):
#         users_collection = await get_collection("users")
#         return await users_collection.insert_one(user_data)

# # 4. Direct usage
# async def some_function():
#     # Auto-ensures connection
#     collection = await get_collection("my_collection")
#     result = await collection.find({}).to_list(length=100)
#     return result

# ================================
# Example 3: Standalone Application
# import asyncio
# from your_mongo_module import mongo_manager

# async def main():
#     try:
#         # Initialize at startup
#         await mongo_manager.initialize()

        # Test basic operations
        # test_collection = await get_collection("test")
        
#         # Your application logic here
#         await run_your_app()

    # except Exception as e:
    #     print(f"Connection test failed: {e}")
        
#     finally:
#         # Cleanup at shutdown
#         await mongo_manager.close()

# if __name__ == "__main__":
#     asyncio.run(main())

# ================================
# Example 4: Service Layer Usage
# from your_mongo_module import mongo_manager, get_collection

# class UserService:
#     async def get_user_by_id(self, user_id: str):
#         users = await get_collection("users")
#         return await users.find_one({"_id": user_id})
    
#     async def create_user(self, user_data: dict):
#         users = await get_collection("users")
#         result = await users.insert_one(user_data)
#         return result.inserted_id
    
#     async def update_user(self, user_id: str, update_data: dict):
#         users = await get_collection("users")
#         return await users.update_one(
#             {"_id": user_id},
#             {"$set": update_data}
#         )
    
#     async def delete_user(self, user_id: str):
#         users = await get_collection("users")
#         return await users.delete_one({"_id": user_id})

# ================================
# Example 8: Multiple Database Usage
# from your_mongo_module import mongo_manager

# class MultiDBService:
#     async def get_user_data(self, user_id: str):
#         # Get from main database
#         main_db = mongo_manager.get_database()
#         user = await main_db.users.find_one({"_id": user_id})
        
#         # Get from analytics database
#         analytics_db = mongo_manager.get_database("analytics")
#         user_stats = await analytics_db.user_stats.find_one({"user_id": user_id})
        
#         return {"user": user, "stats": user_stats}
