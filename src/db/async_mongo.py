"""
Async MongoDB access built on Motor.

    from src.db.async_mongo import mongo_manager, get_collection

    await mongo_manager.initialize()            # once, at startup
    users = await get_collection("users")       # anywhere in your code
    user = await users.find_one({"_id": user_id})
    await mongo_manager.close()                 # at shutdown

Use `mongo_manager.get_database("analytics")` to reach a different database on the
same cluster.
"""

import asyncio
import logging
import time
from typing import Any

import backoff
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
    AsyncIOMotorDatabase,
)

from src.config import Config
from src.db.mongo import mongo_client_kwargs
from src.report.notify import NotificationType, async_report

logger = logging.getLogger(__name__)


class MongoDBManager:
    """Singleton MongoDB manager for async operations"""

    _instance: "MongoDBManager | None" = None
    _lock = asyncio.Lock()

    # How often ensure_connected() actually pings the server. Motor already
    # reconnects on its own, the ping is just an early warning.
    PING_INTERVAL_SECONDS = 30.0

    def __new__(cls) -> "MongoDBManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Only initialize once
        if not hasattr(self, "_attrs_set"):
            self.mongo_uri = Config.MONGO_URI
            self.db_name = Config.MONGO_DB_NAME
            self.max_pool_size = 20
            self.client: AsyncIOMotorClient[Any] | None = None
            self.db: AsyncIOMotorDatabase[Any] | None = None
            self._initialized = False
            self._last_ping: float = 0.0
            self._attrs_set = True

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(self, db_name: str | None = None, max_pool_size: int = 20) -> None:
        """Initialize the MongoDB connection (call once at app startup)"""
        async with self._lock:
            if self._initialized:
                logger.info("MongoDB manager already initialized")
                return

            if db_name:
                self.db_name = db_name
            self.max_pool_size = max_pool_size

            await self._connect()
            self._initialized = True

    def _client_options(self) -> dict[str, Any]:
        return {
            "readPreference": "nearest",
            "localThresholdMS": 30,
            "maxPoolSize": self.max_pool_size,
            "minPoolSize": min(10, self.max_pool_size),
            "maxIdleTimeMS": 120000,
            "waitQueueTimeoutMS": 30000,
            "connectTimeoutMS": 30000,
            "serverSelectionTimeoutMS": 30000,
            "socketTimeoutMS": 30000,
            "retryWrites": True,
            "retryReads": True,
            "directConnection": False,
            **mongo_client_kwargs(),
        }

    async def _connect(self) -> None:
        """Internal method to establish MongoDB connection"""
        try:
            self.client = AsyncIOMotorClient(self.mongo_uri, **self._client_options())
            await self._ping_with_retry()
            self.db = self.client[self.db_name]
            self._last_ping = time.monotonic()
            logger.info("Connected to MongoDB successfully")
        except TimeoutError as e:
            await async_report("MongoDB connection timed out", NotificationType.WARNING)
            await self._cleanup()
            msg = "MongoDB connection timeout"
            raise ConnectionError(msg) from e
        except Exception as e:
            await async_report(f"Failed to connect to MongoDB: {e}", NotificationType.ERROR)
            await self._cleanup()
            raise

    @backoff.on_exception(backoff.expo, Exception, max_tries=3, max_time=10)
    async def _ping_with_retry(self) -> None:
        """Ping MongoDB with exponential backoff retry"""
        if not self.client:
            msg = "MongoDB client not initialized"
            raise RuntimeError(msg)
        await asyncio.wait_for(self.client.admin.command("ping"), timeout=5.0)

    async def ensure_connected(self) -> None:
        """Ensure connection is alive, reconnect if needed.

        Pings at most once per PING_INTERVAL_SECONDS so hot paths don't pay a
        round trip on every query.
        """
        if not self._initialized:
            msg = "MongoDB manager not initialized. Call initialize() first."
            raise RuntimeError(msg)

        if self.client is None:
            await self._connect()
            return

        if time.monotonic() - self._last_ping < self.PING_INTERVAL_SECONDS:
            return

        try:
            await asyncio.wait_for(self.client.admin.command("ping"), timeout=2.0)
            self._last_ping = time.monotonic()
        except Exception as e:
            await async_report(
                f"Connection check failed, reconnecting: {e}", NotificationType.WARNING
            )
            await self._cleanup()
            await self._connect()

    def get_collection(self, collection_name: str) -> AsyncIOMotorCollection[Any]:
        """Get a collection from the default database"""
        if self.db is None:
            msg = "Database not initialized. Call initialize() first."
            raise RuntimeError(msg)
        return self.db[collection_name]

    def get_database(self, db_name: str | None = None) -> AsyncIOMotorDatabase[Any]:
        """Get database instance (current or specified)"""
        if self.client is None:
            msg = "Client not initialized. Call initialize() first."
            raise RuntimeError(msg)

        if db_name:
            return self.client[db_name]

        if self.db is None:
            msg = "Database not initialized. Call initialize() first."
            raise RuntimeError(msg)
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

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on MongoDB connection"""
        try:
            await self.ensure_connected()
            if self.db is None:
                msg = "Database not initialized after connection attempt"
                raise RuntimeError(msg)
            stats = await self.db.command("dbStats")
            return {
                "status": "healthy",
                "database": self.db_name,
                "collections": stats.get("collections", 0),
                "dataSize": stats.get("dataSize", 0),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


# Global singleton instance
mongo_manager = MongoDBManager()


# Convenience functions for easier usage
async def get_collection(collection_name: str) -> AsyncIOMotorCollection[Any]:
    """Get a collection from the default database"""
    await mongo_manager.ensure_connected()
    return mongo_manager.get_collection(collection_name)


async def get_database(db_name: str | None = None) -> AsyncIOMotorDatabase[Any]:
    """Get database instance"""
    await mongo_manager.ensure_connected()
    return mongo_manager.get_database(db_name)
