"""
Async MySQL access built on aiomysql with a shared connection pool.

    from src.db.async_mysql import mysql_manager, fetch_one, execute_query

    await mysql_manager.initialize()                 # once, at startup
    user = await fetch_one("SELECT * FROM users WHERE id = %s", (user_id,))
    rows = await execute_query("SELECT * FROM users WHERE active = %s", (True,))
    await mysql_manager.close()                      # at shutdown

Always pass values through `params`, never format them into the SQL string.
"""

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

import aiomysql

from src.config import Config
from src.report.notify import NotificationType, async_report

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def quote_identifier(name: str) -> str:
    """Validate and backtick-quote a table or column name (optionally schema.table).

    Table and column names cannot be parameterised in SQL, so the helpers that build
    statements from dict keys run every name through this to block injection.
    """
    if not _IDENTIFIER_RE.match(name):
        msg = f"Invalid SQL identifier: {name!r}"
        raise ValueError(msg)
    return ".".join(f"`{part}`" for part in name.split("."))


class MySQLManager:
    """Singleton MySQL manager for async operations with connection pooling"""

    _instance: "MySQLManager | None" = None
    _lock = asyncio.Lock()

    def __new__(cls) -> "MySQLManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Only initialize once
        if not hasattr(self, "_attrs_set"):
            self.host = Config.MYSQL_HOST
            self.port = Config.MYSQL_PORT
            self.user = Config.MYSQL_USER
            self.password = Config.MYSQL_PASSWORD
            self.database = Config.MYSQL_DB
            self.pool_size = 10
            self.pool: Any = None
            self._initialized = False
            self._pool_lock = asyncio.Lock()
            self._attrs_set = True

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    async def initialize(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        pool_size: int = 10,
    ) -> None:
        """Initialize the MySQL connection pool (call once at app startup)"""
        async with self._lock:
            if self._initialized:
                logger.info("MySQL manager already initialized")
                return

            if host:
                self.host = host
            if port:
                self.port = port
            if user:
                self.user = user
            if password is not None:
                self.password = password
            if database:
                self.database = database
            self.pool_size = pool_size

            await self._create_pool()
            self._initialized = True

    async def _create_pool(self) -> None:
        """Internal method to create connection pool"""
        try:
            self.pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.database,
                minsize=1,
                maxsize=self.pool_size,
                autocommit=True,
                charset="utf8mb4",
            )
            logger.info("MySQL connection pool created successfully")
        except Exception as e:
            await async_report(f"Failed to create connection pool: {e}", NotificationType.ERROR)
            raise

    async def ensure_pool(self) -> None:
        """Ensure pool exists, create if needed"""
        if not self._initialized:
            msg = "MySQL manager not initialized. Call initialize() first."
            raise RuntimeError(msg)

        async with self._pool_lock:
            if self.pool is None or self.pool.closed:
                await self._create_pool()

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[Any]:
        """Context manager for getting database connection"""
        await self.ensure_pool()

        conn = await self.pool.acquire()
        try:
            yield conn
        finally:
            self.pool.release(conn)

    async def _run(
        self,
        query: str,
        params: Any,
        *,
        what: str,
        dict_cursor: bool = False,
        fetch: str | None = None,
        many: bool = False,
    ) -> Any:
        """Execute one statement and return rows / rowcount / lastrowid."""
        cursor_type = aiomysql.DictCursor if dict_cursor else None
        async with self.get_connection() as conn, conn.cursor(cursor_type) as cursor:
            try:
                if many:
                    await cursor.executemany(query, params)
                else:
                    await cursor.execute(query, params)
                if fetch == "all":
                    return await cursor.fetchall()
                if fetch == "one":
                    return await cursor.fetchone()
                if fetch == "lastrowid":
                    return cursor.lastrowid
                return cursor.rowcount
            except Exception as e:
                await async_report(f"{what} failed: {e}", NotificationType.ERROR)
                raise

    async def execute_query(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Execute SELECT query and return all rows as dicts"""
        rows = await self._run(query, params, what="Query execution", dict_cursor=True, fetch="all")
        return list(rows)

    async def fetch_one(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None:
        """Execute query and return a single row as dict (or None)"""
        row = await self._run(query, params, what="Fetch one", dict_cursor=True, fetch="one")
        return cast("dict[str, Any] | None", row)

    async def execute_many(self, query: str, params_list: list[tuple[Any, ...]]) -> int:
        """Execute query with multiple parameter sets, return affected rows"""
        count = await self._run(query, params_list, what="Batch execution", many=True)
        return int(count)

    async def execute_raw(self, query: str, params: tuple[Any, ...] | None = None) -> int:
        """Execute raw SQL (INSERT, UPDATE, DELETE) and return affected rows"""
        count = await self._run(query, params, what="Raw query execution")
        return int(count)

    async def execute_transaction(self, queries: list[tuple[str, tuple[Any, ...] | None]]) -> bool:
        """Execute multiple queries in a single transaction (all or nothing)"""
        async with self.get_connection() as conn, conn.cursor() as cursor:
            try:
                await conn.begin()
                for query, params in queries:
                    await cursor.execute(query, params)
                await conn.commit()
                logger.info("Transaction completed successfully")
                return True
            except Exception as e:
                await conn.rollback()
                await async_report(f"Transaction failed, rolled back: {e}", NotificationType.ERROR)
                raise

    async def insert_one(self, table: str, data: dict[str, Any]) -> int:
        """Insert single record and return last insert ID"""
        if not data:
            msg = "insert_one requires at least one column"
            raise ValueError(msg)
        columns = ", ".join(quote_identifier(k) for k in data)
        placeholders = ", ".join(["%s"] * len(data))
        query = f"INSERT INTO {quote_identifier(table)} ({columns}) VALUES ({placeholders})"
        last_id = await self._run(query, tuple(data.values()), what="Insert", fetch="lastrowid")
        return int(last_id)

    async def update_records(
        self, table: str, data: dict[str, Any], where_clause: str, where_params: tuple[Any, ...]
    ) -> int:
        """Update records and return affected row count"""
        if not data:
            msg = "update_records requires at least one column"
            raise ValueError(msg)
        set_clause = ", ".join(f"{quote_identifier(k)} = %s" for k in data)
        query = f"UPDATE {quote_identifier(table)} SET {set_clause} WHERE {where_clause}"
        count = await self._run(query, tuple(data.values()) + tuple(where_params), what="Update")
        return int(count)

    async def delete_records(
        self, table: str, where_clause: str, where_params: tuple[Any, ...]
    ) -> int:
        """Delete records and return affected row count"""
        query = f"DELETE FROM {quote_identifier(table)} WHERE {where_clause}"
        count = await self._run(query, tuple(where_params), what="Delete")
        return int(count)

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on MySQL connection"""
        try:
            await self.ensure_pool()
            result = await self.fetch_one("SELECT 1 as health_check")
            pool_info = {
                "size": self.pool.size if self.pool else 0,
                "free_size": self.pool.freesize if self.pool else 0,
                "max_size": self.pool_size,
            }
            return {
                "status": "healthy",
                "database": self.database,
                "pool_info": pool_info,
                "query_result": result,
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def close(self) -> None:
        """Close the MySQL connection pool (call at app shutdown)"""
        async with self._lock:
            if self.pool is not None:
                self.pool.close()
                await self.pool.wait_closed()
                logger.info("MySQL connection pool closed")
            self.pool = None
            self._initialized = False


# Global singleton instance
mysql_manager = MySQLManager()


# =============================================================
# Convenience functions for easier usage
# =============================================================
async def execute_query(query: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
    """Execute SELECT query and return results"""
    return await mysql_manager.execute_query(query, params)


async def fetch_one(query: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
    """Execute query and return single result"""
    return await mysql_manager.fetch_one(query, params)


async def execute_raw(query: str, params: tuple[Any, ...] | None = None) -> int:
    """Execute INSERT/UPDATE/DELETE and return affected rows"""
    return await mysql_manager.execute_raw(query, params)


async def insert_one(table: str, data: dict[str, Any]) -> int:
    """Insert single record and return last insert ID"""
    return await mysql_manager.insert_one(table, data)


async def update_records(
    table: str, data: dict[str, Any], where_clause: str, where_params: tuple[Any, ...]
) -> int:
    """Update records and return affected row count"""
    return await mysql_manager.update_records(table, data, where_clause, where_params)


async def delete_records(table: str, where_clause: str, where_params: tuple[Any, ...]) -> int:
    """Delete records and return affected row count"""
    return await mysql_manager.delete_records(table, where_clause, where_params)


async def execute_transaction(queries: list[tuple[str, tuple[Any, ...] | None]]) -> bool:
    """Execute multiple queries in a transaction"""
    return await mysql_manager.execute_transaction(queries)
