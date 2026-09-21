from unittest.mock import AsyncMock, MagicMock

import pytest

import src.utils.ws_rate_limiter as ws_module
from src.cache.redis import RedisCacheException
from src.utils.ws_rate_limiter import (
    WS_RATE_LIMIT_CLOSE_CODE,
    WebSocketRateLimiter,
    check_message_rate_limit,
    ws_rate_limit,
)


class FakeCache:
    """In-memory stand-in for RedisCache counters."""

    def __init__(self):
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def increment(self, key, amount=1, ttl=None):
        self.counters[key] = self.counters.get(key, 0) + amount
        if ttl is not None:
            self.ttls[key] = ttl
        return self.counters[key]

    async def get_counter(self, key):
        return self.counters.get(key, 0)


@pytest.fixture
def cache(monkeypatch):
    fake = FakeCache()
    monkeypatch.setattr(ws_module.redis_service, "ensure_connected", AsyncMock(return_value=fake))
    return fake


def make_ws(host="10.0.0.1", headers=None):
    ws = MagicMock()
    ws.headers = headers or {}
    ws.client = MagicMock(host=host) if host else None
    ws.close = AsyncMock()
    ws.accept = AsyncMock()
    return ws


class TestIdentifier:
    def test_uses_client_host(self):
        assert WebSocketRateLimiter._get_client_identifier(make_ws("1.2.3.4")) == "1.2.3.4"

    def test_prefers_first_forwarded_for(self):
        ws = make_ws("10.0.0.1", {"x-forwarded-for": " 203.0.113.9 , 10.0.0.2"})
        assert WebSocketRateLimiter._get_client_identifier(ws) == "203.0.113.9"

    def test_blank_forwarded_for_falls_back(self):
        ws = make_ws("10.0.0.1", {"x-forwarded-for": " , "})
        assert WebSocketRateLimiter._get_client_identifier(ws) == "10.0.0.1"

    def test_unknown_when_no_client(self):
        assert WebSocketRateLimiter._get_client_identifier(make_ws(host=None)) == "unknown"


class TestLimiter:
    def test_validates_arguments(self):
        with pytest.raises(ValueError):
            WebSocketRateLimiter(requests=0, window=60)
        with pytest.raises(ValueError):
            WebSocketRateLimiter(requests=5, window=0)

    def test_key_format(self):
        limiter = WebSocketRateLimiter(5, 60, scope="message")
        assert limiter._get_rate_limit_key("1.1.1.1", "chat") == "ws_ratelimit:message:chat:1.1.1.1"

    async def test_counts_and_blocks(self, cache):
        limiter = WebSocketRateLimiter(requests=2, window=30)
        ws = make_ws()
        assert await limiter.check_rate_limit(ws, "ep") == (True, 1, 2)
        assert await limiter.check_rate_limit(ws, "ep") == (True, 2, 2)
        assert await limiter.check_rate_limit(ws, "ep") == (False, 3, 2)
        assert cache.ttls["ws_ratelimit:connection:ep:10.0.0.1"] == 30

    async def test_clients_are_isolated(self, cache):
        limiter = WebSocketRateLimiter(requests=1, window=30)
        assert (await limiter.check_rate_limit(make_ws("1.1.1.1"), "ep"))[0]
        assert (await limiter.check_rate_limit(make_ws("2.2.2.2"), "ep"))[0]
        assert not (await limiter.check_rate_limit(make_ws("1.1.1.1"), "ep"))[0]

    async def test_remaining_requests(self, cache):
        limiter = WebSocketRateLimiter(requests=3, window=30)
        ws = make_ws()
        assert await limiter.get_remaining_requests(ws, "ep") == (3, 3)
        await limiter.check_rate_limit(ws, "ep")
        await limiter.check_rate_limit(ws, "ep")
        assert await limiter.get_remaining_requests(ws, "ep") == (1, 3)
        await limiter.check_rate_limit(ws, "ep")
        await limiter.check_rate_limit(ws, "ep")
        assert await limiter.get_remaining_requests(ws, "ep") == (0, 3)

    async def test_fails_open_when_redis_down(self, monkeypatch):
        monkeypatch.setattr(
            ws_module.redis_service,
            "ensure_connected",
            AsyncMock(side_effect=RedisCacheException("down")),
        )
        limiter = WebSocketRateLimiter(requests=1, window=30)
        assert await limiter.check_rate_limit(make_ws(), "ep") == (True, 0, 1)

    async def test_fail_closed_when_configured(self, monkeypatch):
        monkeypatch.setattr(
            ws_module.redis_service,
            "ensure_connected",
            AsyncMock(side_effect=RedisCacheException("down")),
        )
        limiter = WebSocketRateLimiter(requests=1, window=30, fail_open=False)
        with pytest.raises(RedisCacheException):
            await limiter.check_rate_limit(make_ws(), "ep")


class TestDecorator:
    async def test_allows_then_closes_with_1008(self, cache):
        calls = []

        @ws_rate_limit(requests=2, window=60)
        async def endpoint(websocket, extra="x"):
            calls.append(extra)
            return "handled"

        ws = make_ws()
        assert await endpoint(ws) == "handled"
        assert await endpoint(websocket=ws, extra="kw") == "handled"
        assert await endpoint(ws) is None
        ws.close.assert_awaited_once()
        kwargs = ws.close.await_args.kwargs
        assert kwargs["code"] == WS_RATE_LIMIT_CLOSE_CODE
        assert "Max 2 connections per 60s" in kwargs["reason"]
        assert calls == ["x", "kw"]
        assert "ws_ratelimit:connection:endpoint:10.0.0.1" in cache.counters

    async def test_preserves_function_metadata(self, cache):
        @ws_rate_limit()
        async def my_socket(websocket):
            """doc"""

        assert my_socket.__name__ == "my_socket"
        assert my_socket.__doc__ == "doc"

    async def test_message_scope_does_not_gate_connection(self, cache):
        @ws_rate_limit(requests=1, window=60, scope="message")
        async def endpoint(websocket):
            return True

        ws = make_ws()
        assert await endpoint(ws)
        assert await endpoint(ws)
        assert cache.counters == {}


class TestMessageHelper:
    async def test_check_message_rate_limit(self, cache):
        ws = make_ws()
        assert await check_message_rate_limit(ws, "gen", requests=2, window=10)
        assert await check_message_rate_limit(ws, "gen", requests=2, window=10)
        assert await check_message_rate_limit(ws, "gen", requests=2, window=10) is False
        assert cache.counters["ws_ratelimit:message:gen:10.0.0.1"] == 3
