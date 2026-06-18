import redis
import redis.asyncio as redis_asyncio

from .config import settings

# Single shared Redis client (online feature store, counters, nonces, pub/sub).
# decode_responses=True so callers get str, not bytes.
redis_client: redis.Redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)

# Async client for the SOC WebSocket feed only (ws.py) -- the sync client above would
# block the asyncio event loop for every connected client if used in a pubsub listen
# loop, so this is a separate connection, not a replacement.
async_redis_client: redis_asyncio.Redis = redis_asyncio.from_url(
    settings.redis_url, decode_responses=True
)


def ping() -> bool:
    """Return True if Redis answers PING."""
    try:
        return bool(redis_client.ping())
    except Exception:
        return False
