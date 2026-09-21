"""
HTTP rate limiting via slowapi.

    from src.utils.rate_limiter import limiter

    @app.get("/things")
    @limiter.limit("10/minute")
    async def things(request: Request): ...

Clients are identified by IP. When running behind a proxy start uvicorn with
`--proxy-headers --forwarded-allow-ips=<proxy ip>` so `request.client.host` is the
real client and not the proxy.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
