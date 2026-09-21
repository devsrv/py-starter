import json
import logging
from datetime import timedelta
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisCacheException(Exception):  # noqa: N818 - public name kept for compatibility
    """Exception raised for Redis cache errors."""


def _ttl_seconds(ttl: int | timedelta | None) -> int | None:
    if isinstance(ttl, timedelta):
        return int(ttl.total_seconds())
    return ttl


class RedisCache:
    """
    A Redis-based cache service with support for various data types and connection pooling.
    Every method raises RedisCacheException when Redis is unreachable or the command fails.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        **kwargs: Any,
    ):
        self.client: redis.Redis | None = None
        self.connection_params: dict[str, Any] = {
            "host": host,
            "port": port,
            "db": db,
            "password": password,
            "decode_responses": True,
            **kwargs,
        }

    @property
    def is_connected(self) -> bool:
        return self.client is not None

    def _require_client(self) -> redis.Redis:
        if self.client is None:
            msg = "Redis is not connected. Call connect() first."
            raise RedisCacheException(msg)
        return self.client

    async def connect(self) -> None:
        """Initialize the async Redis connection and verify it with a PING."""
        try:
            client = redis.Redis(**self.connection_params)
            await client.ping()
            self.client = client
        except Exception as e:
            self.client = None
            msg = f"Failed to connect to Redis: {e}"
            raise RedisCacheException(msg) from e

    async def set(self, key: str, value: Any, ttl: int | timedelta | None = None) -> bool:
        """Store a value. Non-scalar values are JSON encoded."""
        try:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = str(value)
            elif not isinstance(value, (str, bytes)):
                value = json.dumps(value)
            return bool(await self._require_client().set(key, value, ex=_ttl_seconds(ttl)))
        except RedisCacheException:
            raise
        except Exception as e:
            msg = f"Failed to set cache key '{key}': {e}"
            raise RedisCacheException(msg) from e

    async def get(self, key: str, default: Any = None) -> Any:
        """Fetch a value. JSON encoded values are decoded, everything else is returned raw."""
        try:
            value = await self._require_client().get(key)
        except RedisCacheException:
            raise
        except Exception as e:
            msg = f"Failed to get cache key '{key}': {e}"
            raise RedisCacheException(msg) from e

        if value is None:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def has_key(self, key: str) -> bool:
        try:
            return bool(await self._require_client().exists(key))
        except RedisCacheException:
            raise
        except Exception as e:
            msg = f"Failed to check existence of cache key '{key}': {e}"
            raise RedisCacheException(msg) from e

    async def increment(self, key: str, amount: int = 1, ttl: int | timedelta | None = None) -> int:
        """
        Atomically increment a counter. The key is created (starting at 0) if missing.

        When `ttl` is given it is applied on the first increment, and also re-applied
        if the key somehow exists without an expiry, so counters can never live forever.
        """
        try:
            client = self._require_client()
            new_value = await client.incrby(key, amount)
            seconds = _ttl_seconds(ttl)
            if seconds is not None and (new_value == amount or await client.ttl(key) == -1):
                await client.expire(key, seconds)
            return int(new_value)
        except RedisCacheException:
            raise
        except Exception as e:
            msg = f"Failed to increment cache key '{key}': {e}"
            raise RedisCacheException(msg) from e

    async def get_counter(self, key: str) -> int:
        """Current value of a counter (0 if the key doesn't exist)."""
        try:
            value = await self._require_client().get(key)
            return int(value) if value is not None else 0
        except RedisCacheException:
            raise
        except Exception as e:
            msg = f"Failed to get counter value for key '{key}': {e}"
            raise RedisCacheException(msg) from e

    async def delete(self, key: str) -> bool:
        try:
            return bool(await self._require_client().delete(key))
        except RedisCacheException:
            raise
        except Exception as e:
            msg = f"Failed to delete cache key '{key}': {e}"
            raise RedisCacheException(msg) from e

    async def expire(self, key: str, ttl: int | timedelta) -> bool:
        """Set an expiration time for a key. Returns True if the timeout was set."""
        try:
            seconds = _ttl_seconds(ttl)
            assert seconds is not None
            return bool(await self._require_client().expire(key, seconds))
        except RedisCacheException:
            raise
        except Exception as e:
            msg = f"Failed to set expiry for cache key '{key}': {e}"
            raise RedisCacheException(msg) from e

    async def clear(self) -> bool:
        """Clear all keys in the current database."""
        try:
            return bool(await self._require_client().flushdb())
        except RedisCacheException:
            raise
        except Exception as e:
            msg = f"Failed to clear cache: {e}"
            raise RedisCacheException(msg) from e

    async def close(self) -> None:
        """Close the Redis connection"""
        if self.client is not None:
            await self.client.aclose()
            self.client = None
            logger.info("Redis cache connection closed")
