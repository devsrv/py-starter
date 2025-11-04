### WS Rate Limiter Module: `src/utils/ws_rate_limiter.py`

This module provides:

1. **`WebSocketRateLimiter`** class - Core rate limiting logic using Redis
2. **`@ws_rate_limit()`** decorator - Easy-to-use decorator for WebSocket endpoints
3. **`check_message_rate_limit()`** function - Manual rate limiting for individual messages

### How It Works

1. **Client Identification**: Uses client IP address (supports X-Forwarded-For header for proxies)
2. **Redis Tracking**: Uses Redis INCR with TTL to track connection attempts
3. **Rate Limit Check**: Checks before accepting WebSocket connection
4. **Automatic Rejection**: Closes connection with error code 1008 if rate limit exceeded

### Usage

#### Basic Usage (Connection Rate Limiting)

```python
from src.utils.ws_rate_limiter import ws_rate_limit

@router.websocket("/endpoint")
@ws_rate_limit(requests=10, window=60, scope="connection")
@require_ws_auth
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Your WebSocket logic here
```

**Parameters:**

-   `requests`: Maximum number of connections allowed (default: 10)
-   `window`: Time window in seconds (default: 60)
-   `scope`: "connection" for limiting new connections, "message" for limiting messages

#### Advanced Usage (Message Rate Limiting)

For rate limiting individual messages within an active WebSocket connection:

```python
from src.utils.ws_rate_limiter import check_message_rate_limit

@router.websocket("/endpoint")
@require_ws_auth
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()

            # Check rate limit for each message
            if not await check_message_rate_limit(
                websocket,
                "generate",
                requests=20,
                window=60
            ):
                await websocket.send_json({
                    "type": "error",
                    "content": "Rate limit exceeded. Please slow down."
                })
                continue

            # Process message...
    except WebSocketDisconnect:
        pass
```

### Adjusting Rate Limits

To change rate limits, modify the decorator parameters:

```python
# Allow 20 connections per minute
@ws_rate_limit(requests=20, window=60, scope="connection")

# Allow 5 connections per 30 seconds
@ws_rate_limit(requests=5, window=30, scope="connection")

# Allow 100 connections per hour (3600 seconds)
@ws_rate_limit(requests=100, window=3600, scope="connection")
```

## Client Behavior

When a client exceeds the rate limit:

1. **Connection Rejected**: WebSocket connection is closed immediately
2. **Error Code**: 1008 (Policy Violation)
3. **Error Message**: `"Rate limit exceeded. Max {limit} connections per {window}s. Current: {current}"`

### Example Client Handling

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/assessment-agent/generate-assessment')

ws.onerror = (error) => {
	console.error('WebSocket error:', error)
}

ws.onclose = (event) => {
	if (event.code === 1008) {
		console.error('Rate limit exceeded:', event.reason)
		// Wait before retrying
		setTimeout(() => {
			// Retry connection
		}, 60000) // Wait 1 minute
	}
}
```

## Monitoring

The rate limiter uses Redis keys in the format:

```
ws_ratelimit:{scope}:{endpoint}:{client_ip}
```

### Check Rate Limit Status

You can manually check rate limit status in Redis:

```bash
# Connect to Redis
redis-cli

# List all WebSocket rate limit keys
KEYS ws_ratelimit:*

# Check specific client's connection count
GET ws_ratelimit:connection:websocket_generate_single_assessment:192.168.1.100

# Check TTL (time remaining)
TTL ws_ratelimit:connection:websocket_generate_single_assessment:192.168.1.100
```

## Benefits Over slowapi

1. **WebSocket Native**: Designed specifically for WebSocket connections
2. **Redis-Based**: Distributed rate limiting across multiple servers
3. **Flexible Scopes**: Can rate limit both connections and messages
4. **IP-Based**: Tracks clients by IP address (proxy-aware)
5. **Graceful Rejection**: Closes connection with meaningful error message
6. **TTL Support**: Automatic cleanup of rate limit data

## Testing

To test the rate limiter:

```python
import asyncio
from fastapi.testclient import TestClient

def test_websocket_rate_limit():
    with TestClient(app) as client:
        # First 10 connections should succeed
        for i in range(10):
            with client.websocket_connect("/api/v1/assessment-agent/generate-assessment") as ws:
                ws.send_json({"type": "generate", "prompt": "test"})

        # 11th connection should be rejected
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/assessment-agent/generate-assessment") as ws:
                pass
```

## Troubleshooting

### Issue: Rate limit triggered too frequently

**Solution**: Increase the `requests` parameter or `window` duration:

```python
@ws_rate_limit(requests=20, window=60)  # More lenient
```

### Issue: Legitimate clients being blocked

**Solution**:

1. Check if behind a load balancer/proxy - ensure X-Forwarded-For header is set
2. Consider using authentication tokens for rate limiting instead of IP
3. Implement user-based rate limiting

### Issue: Rate limiter not working

**Solution**:

1. Verify Redis is running: `redis-cli ping`
2. Check Redis connection in logs
3. Ensure `ws_rate_limit` decorator is placed BEFORE `@require_ws_auth`

## Future Enhancements

Potential improvements:

1. **Token-based limiting**: Rate limit per authentication token instead of IP
2. **Tiered limits**: Different limits for different user tiers (free/premium)
3. **Dynamic limits**: Adjust limits based on server load
4. **Burst handling**: Allow short bursts above limit
5. **Metrics**: Track rate limit hits for monitoring

## Related Files

-   Implementation: `src/utils/ws_rate_limiter.py`
-   Assessment routes: `src/app/assessment/routes.py`
-   JD routes: `src/app/jd/routes.py`
-   Email routes: `src/app/email/routes.py`
-   Redis service: `src/app/cache/redis_service.py`
-   Redis cache: `src/cache/redis.py`

---

Last Updated: 2025-11-03
