from datetime import timedelta

import fakeredis.aioredis
import pytest

import src.cache.redis as redis_module
from src.cache.redis import RedisCache, RedisCacheException


@pytest.fixture
def fake_server():
    return fakeredis.FakeServer()


@pytest.fixture
def patch_redis(monkeypatch, fake_server):
    created = []

    def factory(**kwargs):
        client = fakeredis.aioredis.FakeRedis(
            server=fake_server, decode_responses=kwargs.get("decode_responses", True)
        )
        created.append(kwargs)
        return client

    monkeypatch.setattr(redis_module.redis, "Redis", factory)
    return created


@pytest.fixture
async def cache(patch_redis):
    c = RedisCache(host="h", port=1234, db=2, password="pw", socket_timeout=5)
    await c.connect()
    yield c
    await c.close()


async def test_connect_passes_connection_params(cache, patch_redis):
    assert cache.is_connected
    assert patch_redis[0] == {
        "host": "h",
        "port": 1234,
        "db": 2,
        "password": "pw",
        "decode_responses": True,
        "socket_timeout": 5,
    }


async def test_methods_require_connection():
    c = RedisCache()
    with pytest.raises(RedisCacheException, match="not connected"):
        await c.get("x")
    with pytest.raises(RedisCacheException, match="not connected"):
        await c.set("x", 1)


async def test_connect_failure_wraps_exception(monkeypatch):
    class Broken:
        def __init__(self, **kwargs):
            pass

        async def ping(self):
            raise ConnectionError("refused")

    monkeypatch.setattr(redis_module.redis, "Redis", Broken)
    c = RedisCache()
    with pytest.raises(RedisCacheException, match="Failed to connect"):
        await c.connect()
    assert not c.is_connected


async def test_set_get_scalars(cache):
    assert await cache.set("s", "text")
    assert await cache.get("s") == "text"
    await cache.set("i", 42)
    assert await cache.get("i") == 42
    await cache.set("f", 1.5)
    assert await cache.get("f") == 1.5
    await cache.set("b", True)
    assert await cache.get("b") is True


async def test_set_get_json(cache):
    payload = {"a": [1, 2], "b": {"c": None}}
    await cache.set("j", payload)
    assert await cache.get("j") == payload
    await cache.set("l", [1, "two"])
    assert await cache.get("l") == [1, "two"]


async def test_get_default(cache):
    assert await cache.get("missing") is None
    assert await cache.get("missing", default="d") == "d"


async def test_non_json_strings_are_returned_raw(cache):
    await cache.set("raw", "{not json")
    assert await cache.get("raw") == "{not json"


async def test_ttl_int_and_timedelta(cache):
    await cache.set("a", "x", ttl=100)
    await cache.set("b", "x", ttl=timedelta(minutes=2))
    assert 0 < await cache.client.ttl("a") <= 100
    assert 0 < await cache.client.ttl("b") <= 120


async def test_has_key_and_delete(cache):
    assert await cache.has_key("k") is False
    await cache.set("k", 1)
    assert await cache.has_key("k")
    assert await cache.delete("k")
    assert await cache.delete("k") is False


async def test_counters(cache):
    assert await cache.get_counter("c") == 0
    assert await cache.increment("c", ttl=60) == 1
    assert await cache.increment("c", amount=5) == 6
    assert await cache.get_counter("c") == 6
    assert 0 < await cache.client.ttl("c") <= 60


async def test_increment_repairs_missing_ttl(cache):
    await cache.client.set("orphan", "3")  # no expiry
    assert await cache.client.ttl("orphan") == -1
    await cache.increment("orphan", ttl=30)
    assert 0 < await cache.client.ttl("orphan") <= 30


async def test_expire_and_clear(cache):
    await cache.set("e", 1)
    assert await cache.expire("e", timedelta(seconds=10))
    assert 0 < await cache.client.ttl("e") <= 10
    assert await cache.expire("nothing", 10) is False
    assert await cache.clear()
    assert await cache.has_key("e") is False


async def test_errors_are_wrapped(cache):
    async def boom(*a, **k):
        raise RuntimeError("redis down")

    cache.client.get = boom
    cache.client.set = boom
    cache.client.incrby = boom
    cache.client.exists = boom
    cache.client.delete = boom
    cache.client.expire = boom
    cache.client.flushdb = boom
    for coro in (
        cache.get("x"),
        cache.set("x", 1),
        cache.increment("x"),
        cache.get_counter("x"),
        cache.has_key("x"),
        cache.delete("x"),
        cache.expire("x", 1),
        cache.clear(),
    ):
        with pytest.raises(RedisCacheException):
            await coro


async def test_close_is_idempotent(cache):
    await cache.close()
    assert cache.is_connected is False
    await cache.close()
