import redis.asyncio as redis
import json
from typing import Any, Optional, Union
from datetime import timedelta


class RedisCacheException(Exception):
    """Exception raised for Redis cache errors."""
    pass


class RedisCache:
    """
    A Redis-based cache service with support for various data types and connection pooling.
    Raises RedisCacheException if Redis is not connectable.
    """
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0, 
                 password: Optional[str] = None, **kwargs):
        self.client = None
        self.connection_params = {
            'host': host,
            'port': port,
            'db': db,
            'password': password,
            'decode_responses': True,
            **kwargs
        }
        
    async def connect(self):
        """Initialize async Redis connection"""
        try:
            self.client = redis.from_url(
                f"redis://{self.connection_params['host']}:{self.connection_params['port']}/{self.connection_params['db']}",
                password=self.connection_params.get('password'),
                decode_responses=True
            )
            await self.client.ping()
        except Exception as e:
            raise Exception(f"Failed to connect to Redis: {str(e)}")
            
    async def set(self, key: str, value: Any, ttl: Optional[Union[int, timedelta]] = None) -> bool:
        try:
            if not isinstance(value, (str, bytes, int, float)):
                value = json.dumps(value)
            elif isinstance(value, (int, float)):
                value = str(value)
                
            if isinstance(ttl, timedelta):
                ttl = int(ttl.total_seconds())
                
            return await self.client.set(key, value, ex=ttl)
        except Exception as e:
            raise Exception(f"Failed to set cache key '{key}': {str(e)}")
            
    async def get(self, key: str, default: Any = None) -> Any:
        try:
            value = await self.client.get(key)
            
            if value is None:
                return default
                
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            raise Exception(f"Failed to get cache key '{key}': {str(e)}")
    
    async def has_key(self, key: str) -> bool:
        try:
            return bool(await self.client.exists(key))
        except Exception as e:
            raise Exception(f"Failed to check existence of cache key '{key}': {str(e)}")
    
    async def increment(self, key: str, amount: int = 1, ttl: Optional[Union[int, timedelta]] = None) -> int:
        """
        Increment a counter by the specified amount. Creates the key with value 0 if it doesn't exist.
        
        Args:
            key: The cache key for the counter
            amount: Amount to increment by (default: 1)
            ttl: Optional time to live for the key
            
        Returns:
            int: The new value after incrementing
            
        Raises:
            RedisCacheException: If the operation fails
        """
        try:
            # Use INCRBY for atomic increment operation
            new_value = await self.client.incrby(key, amount)
            
            # Set TTL if provided (only on first increment when key was created)
            if ttl is not None and new_value == amount:
                if isinstance(ttl, timedelta):
                    ttl = int(ttl.total_seconds())
                await self.client.expire(key, ttl)
                
            return new_value
        except Exception as e:
            raise RedisCacheException(f"Failed to increment cache key '{key}': {str(e)}")
    
    async def get_counter(self, key: str) -> int:
        """
        Get the current value of a counter.
        
        Args:
            key: The cache key for the counter
            
        Returns:
            int: The current counter value (0 if key doesn't exist)
            
        Raises:
            RedisCacheException: If the operation fails
        """
        try:
            value = await self.client.get(key)
            return int(value) if value is not None else 0
        except Exception as e:
            raise RedisCacheException(f"Failed to get counter value for key '{key}': {str(e)}")
    
    async def delete(self, key: str) -> bool:
        try:
            return bool(await self.client.delete(key))
        except Exception as e:
            raise RedisCacheException(f"Failed to delete cache key '{key}': {str(e)}")
    
    async def expire(self, key: str, ttl: Union[int, timedelta]) -> bool:
        """
        Set an expiration time for a key.
        
        Args:
            key: The cache key
            ttl: Time to live in seconds or as a timedelta object
            
        Returns:
            bool: True if the timeout was set
            
        Raises:
            RedisCacheException: If the operation fails
        """
        try:
            if isinstance(ttl, timedelta):
                ttl = int(ttl.total_seconds())
                
            return await self.client.expire(key, ttl)
        except Exception as e:
            raise RedisCacheException(f"Failed to set expiry for cache key '{key}': {str(e)}")
    
    async def clear(self) -> bool:
        """
        Clear all keys in the current database.
        
        Returns:
            bool: True if successful
            
        Raises:
            RedisCacheException: If the operation fails
        """
        try:
            return await self.client.flushdb()
        except Exception as e:
            raise RedisCacheException(f"Failed to clear cache: {str(e)}")
    
    async def close(self) -> None:
        """Close the Redis connection"""
        if self.client:
            await self.client.close()
            print("Redis cache connection closed.")