import asyncio
import logging
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
from src.config import Config
from src.report.notify import NotificationType, async_report

# Import with type ignore to suppress import warnings
import aiomysql  # type: ignore

logger = logging.getLogger(__name__)


class MySQLManager:
    """Singleton MySQL manager for async operations with connection pooling"""
    
    _instance: Optional['MySQLManager'] = None
    _initialized: bool = False
    _lock = asyncio.Lock()
    
    def __new__(cls) -> 'MySQLManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Only initialize once
        if not hasattr(self, '_attrs_set'):
            self.host = Config.MYSQL_HOST
            self.port = Config.MYSQL_PORT
            self.user = Config.MYSQL_USER
            self.password = Config.MYSQL_PASSWORD
            self.database = Config.MYSQL_DB
            self.pool_size = 10
            self.pool: Optional[Any] = None
            self._pool_lock = asyncio.Lock()
            self._attrs_set = True
    
    async def initialize(self,
                        host: Optional[str]=None,
                        port: Optional[int]=None,
                        user: Optional[str]=None,
                        password: Optional[str]=None,
                        database: Optional[str]=None,
                        pool_size: int=10) -> None:
        """Initialize the MySQL connection pool (call once at app startup)"""
        async with self._lock:
            if self._initialized:
                logger.info("MySQL manager already initialized")
                return
            
            # Override defaults if provided
            if host:
                self.host = host
            if port:
                self.port = port
            if user:
                self.user = user
            if password:
                self.password = password
            if database:
                self.database = database
            self.pool_size = pool_size
            
            await self._create_pool()
            self._initialized = True
    
    async def _create_pool(self) -> None:
        """Internal method to create connection pool"""
        try:
            # Suppress the specific warning about create_pool return type
            self.pool = await aiomysql.create_pool(# type: ignore[misc]
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
            await async_report(f"Failed to create connection pool: {e}", NotificationType.ERROR)
            raise
    
    async def ensure_pool(self) -> None:
        """Ensure pool exists, create if needed"""
        if not self._initialized:
            raise RuntimeError("MySQL manager not initialized. Call initialize() first.")
        
        async with self._pool_lock:
            if not self.pool or self.pool._closed:  # type: ignore[misc]
                await self._create_pool()
    
    @asynccontextmanager
    async def get_connection(self):
        """Context manager for getting database connection"""
        await self.ensure_pool()
        
        conn = await self.pool.acquire()  # type: ignore[misc]
        try:
            yield conn
        finally:
            self.pool.release(conn)  # type: ignore[misc]
    
    async def execute_query(self, query: str, params: Optional[tuple[Any, ...]]=None) -> List[Dict[str, Any]]:
        """Execute SELECT query and return results"""
        async with self.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:  # type: ignore[misc]
                try:
                    await cursor.execute(query, params)  # type: ignore[misc]
                    result = await cursor.fetchall()  # type: ignore[misc]
                    return result
                except Exception as e:
                    await async_report(f"Query execution failed: {e}", NotificationType.ERROR)
                    raise
    
    async def execute_many(self, query: str, params_list: List[tuple[Any, ...]]) -> int:
        """Execute query with multiple parameter sets"""
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:  # type: ignore[misc]
                try:
                    await cursor.executemany(query, params_list)  # type: ignore[misc]
                    return cursor.rowcount  # type: ignore[misc]
                except Exception as e:
                    await async_report(f"Batch execution failed: {e}", NotificationType.ERROR)
                    raise
    
    async def execute_transaction(self, queries: List[tuple[str, Optional[tuple[Any, ...]]]]) -> bool:
        """Execute multiple queries in a transaction"""
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
                    await async_report(f"Transaction failed, rolled back: {e}", NotificationType.ERROR)
                    raise
    
    async def insert_one(self, table: str, data: Dict[str, Any]) -> int:
        """Insert single record and return last insert ID"""
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:  # type: ignore[misc]
                try:
                    await cursor.execute(query, tuple(data.values()))  # type: ignore[misc]
                    return cursor.lastrowid  # type: ignore[misc]
                except Exception as e:
                    await async_report(f"Insert failed: {e}", NotificationType.ERROR)
                    raise
    
    async def update_records(self, table: str, data: Dict[str, Any],
                           where_clause: str, where_params: tuple[Any, ...]) -> int:
        """Update records and return affected row count"""
        set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
        params = tuple(data.values()) + where_params
        
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:  # type: ignore[misc]
                try:
                    await cursor.execute(query, params)  # type: ignore[misc]
                    return cursor.rowcount  # type: ignore[misc]
                except Exception as e:
                    await async_report(f"Update failed: {e}", NotificationType.ERROR)
                    raise
    
    async def delete_records(self, table: str, where_clause: str, where_params: tuple[Any, ...]) -> int:
        """Delete records and return affected row count"""
        query = f"DELETE FROM {table} WHERE {where_clause}"
        
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:  # type: ignore[misc]
                try:
                    await cursor.execute(query, where_params)  # type: ignore[misc]
                    return cursor.rowcount  # type: ignore[misc]
                except Exception as e:
                    await async_report(f"Delete failed: {e}", NotificationType.ERROR)
                    raise
    
    async def execute_raw(self, query: str, params: Optional[tuple[Any, ...]]=None) -> int:
        """Execute raw SQL (INSERT, UPDATE, DELETE) and return affected rows"""
        async with self.get_connection() as conn:
            async with conn.cursor() as cursor:  # type: ignore[misc]
                try:
                    await cursor.execute(query, params)  # type: ignore[misc]
                    return cursor.rowcount  # type: ignore[misc]
                except Exception as e:
                    await async_report(f"Raw query execution failed: {e}", NotificationType.ERROR)
                    raise
    
    async def fetch_one(self, query: str, params: Optional[tuple[Any, ...]]=None) -> Optional[Dict[str, Any]]:
        """Execute query and return single result"""
        async with self.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:  # type: ignore[misc]
                try:
                    await cursor.execute(query, params)  # type: ignore[misc]
                    result = await cursor.fetchone()  # type: ignore[misc]
                    return result
                except Exception as e:
                    await async_report(f"Fetch one failed: {e}", NotificationType.ERROR)
                    raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on MySQL connection"""
        try:
            await self.ensure_pool()
            result = await self.fetch_one("SELECT 1 as health_check")
            
            # Get pool statistics
            pool_info = {
                "size": self.pool.size if self.pool else 0,  # type: ignore[misc]
                "free_size": self.pool.freesize if self.pool else 0,  # type: ignore[misc]
                "max_size": self.pool_size
            }
            
            return {
                "status": "healthy",
                "database": self.database,
                "pool_info": pool_info,
                "query_result": result
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def close(self) -> None:
        """Close the MySQL connection pool (call at app shutdown)"""
        async with self._lock:
            if self.pool:
                self.pool.close()  # type: ignore[misc]
                await self.pool.wait_closed()  # type: ignore[misc]
                logger.info("MySQL connection pool closed")
                self.pool = None
                self._initialized = False


# Global singleton instance
mysql_manager = MySQLManager()


# =============================================================
# Convenience functions for easier usage
# =============================================================
async def execute_query(query: str, params: Optional[tuple[Any, ...]]=None) -> List[Dict[str, Any]]:
    """Execute SELECT query and return results"""
    await mysql_manager.ensure_pool()
    return await mysql_manager.execute_query(query, params)


async def fetch_one(query: str, params: Optional[tuple[Any, ...]]=None) -> Optional[Dict[str, Any]]:
    """Execute query and return single result"""
    await mysql_manager.ensure_pool()
    return await mysql_manager.fetch_one(query, params)


async def insert_one(table: str, data: Dict[str, Any]) -> int:
    """Insert single record and return last insert ID"""
    await mysql_manager.ensure_pool()
    return await mysql_manager.insert_one(table, data)


async def update_records(table: str, data: Dict[str, Any], where_clause: str, where_params: tuple[Any, ...]) -> int:
    """Update records and return affected row count"""
    await mysql_manager.ensure_pool()
    return await mysql_manager.update_records(table, data, where_clause, where_params)


async def delete_records(table: str, where_clause: str, where_params: tuple[Any, ...]) -> int:
    """Delete records and return affected row count"""
    await mysql_manager.ensure_pool()
    return await mysql_manager.delete_records(table, where_clause, where_params)


async def execute_transaction(queries: List[tuple[str, Optional[tuple[Any, ...]]]]) -> bool:
    """Execute multiple queries in a transaction"""
    await mysql_manager.ensure_pool()
    return await mysql_manager.execute_transaction(queries)

# Usage examples in comments:

# # 1. In your main application startup
# async def startup():
#     await mysql_manager.initialize()
#     # or with custom settings:
#     # await mysql_manager.initialize(
#     #     host="localhost", 
#     #     port=3306, 
#     #     user="user", 
#     #     password="pass", 
#     #     database="mydb", 
#     #     pool_size=20
#     # )

# # 2. In your application shutdown
# async def shutdown():
#     await mysql_manager.close()

# # 3. In any service/module - no need to pass client around
# from path.to.this.file import mysql_manager, execute_query, insert_one

# class UserService:
#     async def get_user(self, user_id: int):
#         return await fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
    
#     async def create_user(self, user_data: dict):
#         return await insert_one("users", user_data)
    
#     async def update_user(self, user_id: int, user_data: dict):
#         return await update_records("users", user_data, "id = %s", (user_id,))

# # 4. Direct usage with convenience functions
# async def some_function():
#     # Auto-ensures pool connection
#     users = await execute_query("SELECT * FROM users WHERE active = %s", (True,))
#     return users

# # 5. Transaction example
# async def transfer_money(from_account: int, to_account: int, amount: float):
#     queries = [
#         ("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, from_account)),
#         ("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, to_account)),
#         ("INSERT INTO transactions (from_account, to_account, amount) VALUES (%s, %s, %s)", 
#          (from_account, to_account, amount))
#     ]
#     return await execute_transaction(queries)
