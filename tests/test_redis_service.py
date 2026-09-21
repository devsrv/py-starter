from unittest.mock import AsyncMock

import pytest

from src.cache.redis import RedisCache, RedisCacheException
from src.cache.redis_service import RedisService, redis_service
from src.config import Config


@pytest.fixture
def connect_spy(monkeypatch):
    spy = AsyncMock()

    async def fake_connect(self):
        self.client = object()  # mark as connected
        await spy()

    monkeypatch.setattr(RedisCache, "connect", fake_connect)
    monkeypatch.setattr(RedisCache, "close", AsyncMock())
    return spy


async def test_connects_once_and_uses_config(connect_spy):
    svc = RedisService()
    a = await svc.ensure_connected()
    b = await svc.ensure_connected()
    assert a is b
    assert connect_spy.await_count == 1
    assert a.connection_params["host"] == Config.REDIS_HOST
    assert a.connection_params["port"] == Config.REDIS_PORT
    assert a.connection_params["db"] == Config.REDIS_DB


async def test_reconnects_after_close(connect_spy):
    svc = RedisService()
    await svc.ensure_connected()
    await svc.close()
    await svc.ensure_connected()
    assert connect_spy.await_count == 2


async def test_connection_error_propagates(monkeypatch):
    async def failing(self):
        raise RedisCacheException("nope")

    monkeypatch.setattr(RedisCache, "connect", failing)
    svc = RedisService()
    with pytest.raises(RedisCacheException):
        await svc.ensure_connected()


def test_module_singleton():
    assert isinstance(redis_service, RedisService)
