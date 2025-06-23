import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from src.config import Config
from src.report.notify import NotificationType, async_report

# Import with type ignore to suppress import warnings
import aiomysql # type: ignore

logger = logging.getLogger(__name__)

class MySQLClient:
    """Async MySQL client with type warnings suppressed."""
    
    def __init__(self, host: str = Config.MYSQL_HOST, port: int = Config.MYSQL_PORT, user: str = Config.MYSQL_USER, password: str = Config.MYSQL_PASSWORD, database: str = Config.MYSQL_DB, pool_size: int = 10):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self.pool: Optional[Any] = None
    
    async def create_pool(self) -> None:
        """Create connection pool."""
        try:
            # Suppress the specific warning about create_pool return type
            self.pool = await aiomysql.create_pool(  # type: ignore[misc]
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                minsize=1,
                maxsize=self.pool_size,
                autocommit=True,
                charset='utf8mb4'
            )
            logger.info("MySQL connection pool created successfully")
        except Exception as e:
            await async_report(f"Failed to create connection pool: {(e)}", NotificationType.ERROR)
            raise
    
    async def close_pool(self) -> None:
        """Close connection pool."""
        if self.pool:
            self.pool.close()  # type: ignore[misc]
            await self.pool.wait_closed()  # type: ignore[misc]
            logger.info("MySQL connection pool closed")
    
    @asynccontextmanager
    async def get_connection(self):
        """Context manager for getting database connection."""
        if not self.pool:
            await self.create_pool()
        
        conn = await self.pool.acquire()  # type: ignore[misc]
        try:
            yield conn
        finally:
            self.pool.release(conn)  # type: ignore[misc]
    
    async def execute_query(self, query: str, params: Optional[tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
        """Execute SELECT query and return results."""
        async with self.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:  # type: ignore[misc]
                try:
                    await cursor.execute(query, params)  # type: ignore[misc]
                    result = await cursor.fetchall()  # type: ignore[misc]
                    return result
                except Exception as e:
                    await async_report(f"Query execution failed: {(e)}", NotificationType.ERROR)
                    raise
    
    async def execute_many(self, query: str, params_list: List[tuple[Any, ...]]) -> int:
        """Execute query with multiple parameter sets."""
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:  # type: ignore[misc]
                try:
                    await cursor.executemany(query, params_list)  # type: ignore[misc]
                    return cursor.rowcount  # type: ignore[misc]
                except Exception as e:
                    await async_report(f"Batch execution failed: {(e)}", NotificationType.ERROR)
                    raise
    
    async def execute_transaction(self, queries: List[tuple[str, Optional[tuple[Any, ...]]]]) -> bool:
        """Execute multiple queries in a transaction."""
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:  # type: ignore[misc]
                try:
                    await conn.begin()  # type: ignore[misc]
                    
                    for query, params in queries:
                        await cursor.execute(query, params)  # type: ignore[misc]
                    
                    await conn.commit()  # type: ignore[misc]
                    logger.info("Transaction completed successfully")
                    return True
                    
                except Exception as e:
                    await conn.rollback()  # type: ignore[misc]
                    await async_report(f"Transaction failed, rolled back: {(e)}", NotificationType.ERROR)
                    raise
    
    async def insert_one(self, table: str, data: Dict[str, Any]) -> int:
        """Insert single record and return last insert ID."""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:  # type: ignore[misc]
                try:
                    await cursor.execute(query, tuple(data.values()))  # type: ignore[misc]
                    return cursor.lastrowid  # type: ignore[misc]
                except Exception as e:
                    await async_report(f"Insert failed: {(e)}", NotificationType.ERROR)
                    raise
    
    async def update_records(self, table: str, data: Dict[str, Any], 
                           where_clause: str, where_params: tuple[Any, ...]) -> int:
        """Update records and return affected row count."""
        set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        params = tuple(data.values()) + where_params
        
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:  # type: ignore[misc]
                try:
                    await cursor.execute(query, params)  # type: ignore[misc]
                    return cursor.rowcount  # type: ignore[misc]
                except Exception as e:
                    await async_report(f"Update failed: {(e)}", NotificationType.ERROR)
                    raise