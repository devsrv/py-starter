"""
Process-wide Redis connection.

Mirrors how `mongo_manager` and `mysql_manager` work: a single lazily-connected
`RedisCache` that any module can grab with `await redis_service.ensure_connected()`.
"""

import asyncio
import logging

from src.cache.redis import RedisCache
from src.config import Config

logger = logging.getLogger(__name__)


class RedisService:
    def __init__(self) -> None:
        self._cache: RedisCache | None = None
        self._lock = asyncio.Lock()

    def _build(self) -> RedisCache:
        return RedisCache(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=Config.REDIS_DB,
            password=Config.REDIS_PASSWORD,
        )

    async def ensure_connected(self) -> RedisCache:
        """Return the shared cache, connecting on first use."""
        if self._cache is not None and self._cache.is_connected:
            return self._cache

        async with self._lock:
            if self._cache is None or not self._cache.is_connected:
                cache = self._cache or self._build()
                await cache.connect()
                self._cache = cache
                logger.info("Connected to Redis at %s:%s", Config.REDIS_HOST, Config.REDIS_PORT)
        return self._cache

    async def close(self) -> None:
        async with self._lock:
            if self._cache is not None:
                await self._cache.close()
                self._cache = None


redis_service = RedisService()
