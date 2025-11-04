"""
WebSocket Rate Limiter using Redis

This module provides rate limiting functionality for WebSocket endpoints.
Unlike HTTP rate limiting, WebSocket rate limiting tracks:
1. Connection attempts per time window
2. Message/generation requests per connection
"""

import time
from functools import wraps
from typing import Callable, Optional
from fastapi import WebSocket
from src.app.cache.redis_service import redis_service


class WebSocketRateLimitExceeded(Exception):
    """Raised when WebSocket rate limit is exceeded"""
    pass


class WebSocketRateLimiter:
    """
    WebSocket rate limiter using Redis for tracking.

    Supports two types of rate limiting:
    1. Connection rate limiting - limits new WebSocket connections
    2. Message rate limiting - limits messages sent through an active connection
    """

    def __init__(self, requests: int, window: int, scope: str = "connection"):
        """
        Initialize rate limiter

        Args:
            requests: Maximum number of requests allowed
            window: Time window in seconds
            scope: "connection" for limiting connections, "message" for limiting messages
        """
        self.requests = requests
        self.window = window
        self.scope = scope

    def _get_client_identifier(self, websocket: WebSocket) -> str:
        """
        Extract client identifier from WebSocket.
        Uses IP address as the primary identifier.
        """
        # Try to get real IP from headers (in case behind proxy)
        forwarded_for = websocket.headers.get("x-forwarded-for")
        if forwarded_for:
            # Get first IP in the chain
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            # Fallback to direct client IP
            client_ip = websocket.client.host if websocket.client else "unknown"

        # TODO: add support for authenticated users and their email/ID as identifier
        return client_ip

    def _get_rate_limit_key(self, client_id: str, endpoint: str) -> str:
        """Generate Redis key for rate limiting"""
        return f"ws_ratelimit:{self.scope}:{endpoint}:{client_id}"

    async def check_rate_limit(self, websocket: WebSocket, endpoint: str) -> tuple[bool, int, int]:
        """
        Check if client has exceeded rate limit.

        Args:
            websocket: FastAPI WebSocket instance
            endpoint: Endpoint identifier (e.g., "/generate-assessment")

        Returns:
            Tuple of (is_allowed, current_count, limit)
        """
        client_id = self._get_client_identifier(websocket)
        key = self._get_rate_limit_key(client_id, endpoint)

        cache = await redis_service.ensure_connected()

        # Increment counter with TTL
        current_count = await cache.increment(key, amount=1, ttl=self.window)

        # Check if limit exceeded
        is_allowed = current_count <= self.requests

        return is_allowed, current_count, self.requests

    async def get_remaining_requests(self, websocket: WebSocket, endpoint: str) -> tuple[int, int]:
        """
        Get remaining requests for the client.

        Returns:
            Tuple of (remaining, limit)
        """
        client_id = self._get_client_identifier(websocket)
        key = self._get_rate_limit_key(client_id, endpoint)

        cache = await redis_service.ensure_connected()
        current_count = await cache.get_counter(key)

        remaining = max(0, self.requests - current_count)
        return remaining, self.requests


def ws_rate_limit(requests: int = 10, window: int = 60, scope: str = "connection"):
    """
    Decorator for WebSocket endpoints to enforce rate limiting.

    Usage:
        @router.websocket("/endpoint")
        @ws_rate_limit(requests=10, window=60, scope="connection")
        @require_ws_auth
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
        - For "message" scope, you should call the rate limiter manually in your message loop
    """
    limiter = WebSocketRateLimiter(requests=requests, window=window, scope=scope)

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(websocket: WebSocket, *args, **kwargs):
            # Extract endpoint name from function
            endpoint = func.__name__

            if scope == "connection":
                # Check rate limit before accepting connection
                is_allowed, current, limit = await limiter.check_rate_limit(websocket, endpoint)

                if not is_allowed:
                    # Close connection immediately if rate limit exceeded
                    await websocket.close(
                        code=1008,
                        reason=f"Rate limit exceeded. Max {limit} connections per {window}s. Current: {current}"
                    )
                    return

            # Proceed with the WebSocket handler
            return await func(websocket, *args, **kwargs)

        return wrapper
    return decorator


async def check_message_rate_limit(
    websocket: WebSocket,
    endpoint: str,
    requests: int = 20,
    window: int = 60
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

                    # Check rate limit before processing message
                    if not await check_message_rate_limit(websocket, "generate", requests=20, window=60):
                        await websocket.send_json({
                            "type": "error",
                            "content": "Rate limit exceeded. Please slow down."
                        })
                        continue

                    # Process message...
            except WebSocketDisconnect:
                pass

    Args:
        websocket: FastAPI WebSocket instance
        endpoint: Endpoint identifier
        requests: Maximum requests allowed
        window: Time window in seconds

    Returns:
        bool: True if allowed, False if rate limit exceeded
    """
    limiter = WebSocketRateLimiter(requests=requests, window=window, scope="message")
    is_allowed, current, limit = await limiter.check_rate_limit(websocket, endpoint)
    return is_allowed
