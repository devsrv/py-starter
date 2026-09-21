from unittest.mock import AsyncMock

import aiomysql
import pytest

import src.db.async_mysql as mysql_module
from src.config import Config
from src.db.async_mysql import (
    MySQLManager,
    delete_records,
    execute_query,
    execute_raw,
    execute_transaction,
    fetch_one,
    insert_one,
    mysql_manager,
    quote_identifier,
    update_records,
)


class FakeCursor:
    def __init__(self, conn, cursor_type):
        self.conn = conn
        self.cursor_type = cursor_type
        self.execute = AsyncMock(side_effect=self._exec)
        self.executemany = AsyncMock(side_effect=self._exec)
        self.fetchall = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
        self.fetchone = AsyncMock(return_value={"id": 1})
        self.rowcount = 3
        self.lastrowid = 42

    async def _exec(self, query, params=None):
        self.conn.pool.executed.append((query, params))
        if self.conn.pool.fail_query:
            raise RuntimeError("syntax error")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    def __init__(self, pool):
        self.pool = pool
        self.begin = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.cursors: list[FakeCursor] = []

    def cursor(self, cursor_type=None):
        c = FakeCursor(self, cursor_type)
        self.cursors.append(c)
        return c


class FakePool:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.executed: list = []
        self.fail_query = False
        self.acquired = 0
        self.released = 0
        self.size = 2
        self.freesize = 1
        self.conn = FakeConn(self)

    async def acquire(self):
        self.acquired += 1
        return self.conn

    def release(self, conn):
        self.released += 1

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


@pytest.fixture
def fake_pool(monkeypatch):
    pools: list[FakePool] = []

    async def create_pool(**kwargs):
        pool = FakePool(**kwargs)
        pools.append(pool)
        return pool

    monkeypatch.setattr(mysql_module.aiomysql, "create_pool", create_pool)
    monkeypatch.setattr(mysql_module, "async_report", AsyncMock())
    mysql_manager.pool = None
    mysql_manager._initialized = False
    mysql_manager.host = Config.MYSQL_HOST
    mysql_manager.database = Config.MYSQL_DB
    yield pools
    mysql_manager.pool = None
    mysql_manager._initialized = False


def test_singleton():
    assert MySQLManager() is mysql_manager


class TestQuoteIdentifier:
    @pytest.mark.parametrize(
        "name,expected", [("users", "`users`"), ("db.users", "`db`.`users`"), ("_x1", "`_x1`")]
    )
    def test_valid(self, name, expected):
        assert quote_identifier(name) == expected

    @pytest.mark.parametrize(
        "bad", ["", "1abc", "users; DROP TABLE x", "a b", "a`b", "a.b.c", "a-b"]
    )
    def test_invalid(self, bad):
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            quote_identifier(bad)


class TestInitialize:
    async def test_uses_config_defaults(self, fake_pool):
        await mysql_manager.initialize()
        [pool] = fake_pool
        assert pool.kwargs["host"] == Config.MYSQL_HOST
        assert pool.kwargs["port"] == Config.MYSQL_PORT
        assert pool.kwargs["db"] == Config.MYSQL_DB
        assert pool.kwargs["maxsize"] == 10
        assert pool.kwargs["autocommit"] is True
        assert pool.kwargs["charset"] == "utf8mb4"
        assert mysql_manager.is_initialized

    async def test_overrides(self, fake_pool):
        await mysql_manager.initialize(
            host="db.internal", port=3307, user="u", password="", database="d", pool_size=3
        )
        [pool] = fake_pool
        assert pool.kwargs["host"] == "db.internal"
        assert pool.kwargs["port"] == 3307
        assert pool.kwargs["user"] == "u"
        assert pool.kwargs["password"] == ""
        assert pool.kwargs["db"] == "d"
        assert pool.kwargs["maxsize"] == 3

    async def test_idempotent(self, fake_pool):
        await mysql_manager.initialize()
        await mysql_manager.initialize(host="other")
        assert len(fake_pool) == 1

    async def test_create_pool_failure_reports_and_raises(self, monkeypatch):
        async def boom(**kwargs):
            raise OSError("no route")

        report = AsyncMock()
        monkeypatch.setattr(mysql_module.aiomysql, "create_pool", boom)
        monkeypatch.setattr(mysql_module, "async_report", report)
        mysql_manager.pool = None
        mysql_manager._initialized = False
        with pytest.raises(OSError):
            await mysql_manager.initialize()
        report.assert_awaited()
        assert not mysql_manager.is_initialized


class TestQueries:
    async def test_execute_query_uses_dict_cursor(self, fake_pool):
        await mysql_manager.initialize()
        rows = await execute_query("SELECT * FROM t WHERE a = %s", (1,))
        assert rows == [{"id": 1}, {"id": 2}]
        pool = fake_pool[0]
        assert pool.executed == [("SELECT * FROM t WHERE a = %s", (1,))]
        assert pool.conn.cursors[0].cursor_type is aiomysql.DictCursor
        assert pool.acquired == pool.released == 1

    async def test_fetch_one(self, fake_pool):
        await mysql_manager.initialize()
        assert await fetch_one("SELECT 1") == {"id": 1}

    async def test_execute_raw_and_many(self, fake_pool):
        await mysql_manager.initialize()
        assert await execute_raw("DELETE FROM t") == 3
        assert await mysql_manager.execute_many("INSERT INTO t VALUES (%s)", [(1,), (2,)]) == 3
        assert fake_pool[0].executed[-1] == ("INSERT INTO t VALUES (%s)", [(1,), (2,)])

    async def test_insert_one_builds_quoted_sql(self, fake_pool):
        await mysql_manager.initialize()
        last_id = await insert_one("users", {"name": "a", "age": 3})
        assert last_id == 42
        query, params = fake_pool[0].executed[0]
        assert query == "INSERT INTO `users` (`name`, `age`) VALUES (%s, %s)"
        assert params == ("a", 3)

    async def test_insert_one_rejects_injection_in_identifiers(self, fake_pool):
        await mysql_manager.initialize()
        with pytest.raises(ValueError):
            await insert_one("users; DROP TABLE users", {"a": 1})
        with pytest.raises(ValueError):
            await insert_one("users", {"a=1; --": 1})
        with pytest.raises(ValueError):
            await insert_one("users", {})
        assert fake_pool[0].executed == []

    async def test_update_records(self, fake_pool):
        await mysql_manager.initialize()
        count = await update_records(
            "users", {"name": "b", "active": True}, "id = %s AND org = %s", (7, 2)
        )
        assert count == 3
        query, params = fake_pool[0].executed[0]
        assert query == "UPDATE `users` SET `name` = %s, `active` = %s WHERE id = %s AND org = %s"
        assert params == ("b", True, 7, 2)
        with pytest.raises(ValueError):
            await update_records("users", {}, "id = %s", (1,))

    async def test_delete_records(self, fake_pool):
        await mysql_manager.initialize()
        assert await delete_records("db.users", "id = %s", (1,)) == 3
        assert fake_pool[0].executed[0] == ("DELETE FROM `db`.`users` WHERE id = %s", (1,))

    async def test_query_failure_reports_and_reraises(self, fake_pool, monkeypatch):
        report = AsyncMock()
        monkeypatch.setattr(mysql_module, "async_report", report)
        await mysql_manager.initialize()
        fake_pool[0].fail_query = True
        with pytest.raises(RuntimeError):
            await execute_query("SELECT bad")
        report.assert_awaited()
        assert fake_pool[0].released == 1  # connection returned to pool


class TestTransaction:
    async def test_commit(self, fake_pool):
        await mysql_manager.initialize()
        ok = await execute_transaction(
            [("UPDATE a SET x = %s", (1,)), ("INSERT INTO b VALUES (%s)", (2,))]
        )
        assert ok is True
        conn = fake_pool[0].conn
        conn.begin.assert_awaited_once()
        conn.commit.assert_awaited_once()
        conn.rollback.assert_not_awaited()
        assert [q for q, _ in fake_pool[0].executed] == [
            "UPDATE a SET x = %s",
            "INSERT INTO b VALUES (%s)",
        ]

    async def test_rollback_on_failure(self, fake_pool):
        await mysql_manager.initialize()
        fake_pool[0].fail_query = True
        with pytest.raises(RuntimeError):
            await execute_transaction([("UPDATE a SET x = 1", None)])
        conn = fake_pool[0].conn
        conn.rollback.assert_awaited_once()
        conn.commit.assert_not_awaited()


class TestPoolLifecycle:
    async def test_ensure_pool_requires_initialize(self, fake_pool):
        with pytest.raises(RuntimeError, match="not initialized"):
            await execute_query("SELECT 1")

    async def test_ensure_pool_recreates_closed_pool(self, fake_pool):
        await mysql_manager.initialize()
        fake_pool[0].closed = True
        await fetch_one("SELECT 1")
        assert len(fake_pool) == 2
        assert mysql_manager.pool is fake_pool[1]

    async def test_close(self, fake_pool):
        await mysql_manager.initialize()
        await mysql_manager.close()
        assert fake_pool[0].closed
        assert mysql_manager.pool is None
        assert not mysql_manager.is_initialized
        await mysql_manager.close()  # idempotent

    async def test_health_check(self, fake_pool):
        await mysql_manager.initialize()
        health = await mysql_manager.health_check()
        assert health["status"] == "healthy"
        assert health["database"] == Config.MYSQL_DB
        assert health["pool_info"] == {"size": 2, "free_size": 1, "max_size": 10}
        assert health["query_result"] == {"id": 1}

    async def test_health_check_unhealthy(self, fake_pool):
        health = await mysql_manager.health_check()
        assert health["status"] == "unhealthy"
