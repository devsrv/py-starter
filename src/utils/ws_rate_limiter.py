"""
WebSocket Rate Limiter using Redis

This module provides rate limiting functionality for WebSocket endpoints.
Unlike HTTP rate limiting, WebSocket rate limiting tracks:
1. Connection attempts per time window
2. Message/generation requests per connection
"""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from fastapi import WebSocket

from src.cache.redis_service import redis_service

logger = logging.getLogger(__name__)

# 1008 = Policy Violation
WS_RATE_LIMIT_CLOSE_CODE = 1008


class WebSocketRateLimitExceeded(Exception):  # noqa: N818 - public name kept for compatibility
    """Raised when WebSocket rate limit is exceeded"""


class WebSocketRateLimiter:
    """
    WebSocket rate limiter using Redis for tracking.

    Supports two types of rate limiting:
    1. Connection rate limiting - limits new WebSocket connections
    2. Message rate limiting - limits messages sent through an active connection

    If Redis is unreachable the limiter fails open (allows the request) and logs an
    error, so a cache outage never takes down your WebSocket endpoints.
    """

    def __init__(
        self, requests: int, window: int, scope: str = "connection", fail_open: bool = True
    ):
        """
        Args:
            requests: Maximum number of requests allowed
            window: Time window in seconds
            scope: "connection" for limiting connections, "message" for limiting messages
            fail_open: Allow requests when Redis is unavailable (default True)
        """
        if requests < 1 or window < 1:
            msg = "requests and window must both be >= 1"
            raise ValueError(msg)
        self.requests = requests
        self.window = window
        self.scope = scope
        self.fail_open = fail_open

    @staticmethod
    def _get_client_identifier(websocket: WebSocket) -> str:
        """
        Extract client identifier from WebSocket. Uses the IP address, honouring
        X-Forwarded-For when the app sits behind a proxy.
        """
        forwarded_for = websocket.headers.get("x-forwarded-for")
        if forwarded_for:
            first = forwarded_for.split(",")[0].strip()
            if first:
                return first
        return websocket.client.host if websocket.client else "unknown"

    def _get_rate_limit_key(self, client_id: str, endpoint: str) -> str:
        """Generate Redis key for rate limiting"""
        return f"ws_ratelimit:{self.scope}:{endpoint}:{client_id}"

    async def check_rate_limit(self, websocket: WebSocket, endpoint: str) -> tuple[bool, int, int]:
        """
        Count this request and report whether the client is still within its limit.

        Returns:
            Tuple of (is_allowed, current_count, limit)
        """
        client_id = self._get_client_identifier(websocket)
        key = self._get_rate_limit_key(client_id, endpoint)

        try:
            cache = await redis_service.ensure_connected()
            current_count = await cache.increment(key, amount=1, ttl=self.window)
        except Exception as e:
            logger.error("WebSocket rate limiter could not reach Redis: %s", e)
            if self.fail_open:
                return True, 0, self.requests
            raise

        return current_count <= self.requests, current_count, self.requests

    async def get_remaining_requests(self, websocket: WebSocket, endpoint: str) -> tuple[int, int]:
        """
        Get remaining requests for the client without counting this call.

        Returns:
            Tuple of (remaining, limit)
        """
        client_id = self._get_client_identifier(websocket)
        key = self._get_rate_limit_key(client_id, endpoint)

        cache = await redis_service.ensure_connected()
        current_count = await cache.get_counter(key)

        return max(0, self.requests - current_count), self.requests


def ws_rate_limit(
    requests: int = 10, window: int = 60, scope: str = "connection"
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """
    Decorator for WebSocket endpoints to enforce rate limiting.

    Usage:
        @router.websocket("/endpoint")
        @ws_rate_limit(requests=10, window=60, scope="connection")
        async def my_endpoint(websocket: WebSocket):
            await websocket.accept()
            # Your code here

    Args:
        requests: Maximum number of requests allowed
        window: Time window in seconds (e.g., 60 for 1 minute)
        scope: "connection" for limiting initial connections,
               "message" for limiting messages (check on each message)

    Note:
        - For "connection" scope, the rate limit is checked BEFORE accepting the connection
        - For "message" scope, call `check_message_rate_limit()` inside your message loop
    """
    limiter = WebSocketRateLimiter(requests=requests, window=window, scope=scope)

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(websocket: WebSocket, *args: Any, **kwargs: Any) -> Any:
            endpoint = func.__name__

            if scope == "connection":
                is_allowed, current, limit = await limiter.check_rate_limit(websocket, endpoint)
                if not is_allowed:
                    await websocket.close(
                        code=WS_RATE_LIMIT_CLOSE_CODE,
                        reason=f"Rate limit exceeded. Max {limit} connections per {window}s. Current: {current}",
                    )
                    return None

            return await func(websocket, *args, **kwargs)

        return wrapper

    return decorator


async def check_message_rate_limit(
    websocket: WebSocket, endpoint: str, requests: int = 20, window: int = 60
) -> bool:
    """
    Manually check rate limit for WebSocket messages.
    Use this inside your WebSocket message loop to rate limit individual messages.

    Usage:
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            try:
                while True:
                    data = await websocket.receive_text()

                    if not await check_message_rate_limit(websocket, "generate", requests=20, window=60):
                        await websocket.send_json({"type": "error", "content": "Rate limit exceeded."})
                        continue

                    # Process message...
            except WebSocketDisconnect:
                pass

    Returns:
        bool: True if allowed, False if rate limit exceeded
    """
    limiter = WebSocketRateLimiter(requests=requests, window=window, scope="message")
    is_allowed, _current, _limit = await limiter.check_rate_limit(websocket, endpoint)
    return is_allowed
