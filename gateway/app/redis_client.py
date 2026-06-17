import redis

from .config import settings

# Single shared Redis client (online feature store, counters, nonces, pub/sub).
# decode_responses=True so callers get str, not bytes.
redis_client: redis.Redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def ping() -> bool:
    """Return True if Redis answers PING."""
    try:
        return bool(redis_client.ping())
    except Exception:
        return False
