import json
import logging
import time
from typing import Any, Dict, Optional, Tuple
import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory fallback cache: key -> (value_json, expiry_timestamp)
_memory_cache: Dict[str, Tuple[str, float]] = {}


class CacheService:
    """Caching service supporting Redis with graceful fallback to in-memory cache."""

    _redis_client: Optional[aioredis.Redis] = None
    _redis_available: Optional[bool] = None

    @classmethod
    async def get_client(cls) -> Optional[aioredis.Redis]:
        if cls._redis_available is False:
            return None
        if cls._redis_client is None and settings.REDIS_URL:
            try:
                client = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                )
                await client.ping()
                cls._redis_client = client
                cls._redis_available = True
                logger.info("Connected to Redis cache successfully.")
            except Exception as e:
                logger.warning("Redis unavailable (%s), falling back to in-memory cache.", e)
                cls._redis_available = False
                cls._redis_client = None
        return cls._redis_client

    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        """Retrieve value from cache by key."""
        try:
            client = await cls.get_client()
            if client:
                val = await client.get(key)
                if val:
                    return json.loads(val)
        except Exception as e:
            logger.debug("Redis get error for %s: %s", key, e)

        # Fallback to in-memory cache
        if key in _memory_cache:
            val_json, exp = _memory_cache[key]
            if time.time() < exp:
                return json.loads(val_json)
            del _memory_cache[key]
        return None

    @classmethod
    async def set(cls, key: str, value: Any, ttl: int = 60) -> None:
        """Store value in cache with TTL in seconds."""
        encoded = json.dumps(value, default=str)
        try:
            client = await cls.get_client()
            if client:
                await client.set(key, encoded, ex=ttl)
                return
        except Exception as e:
            logger.debug("Redis set error for %s: %s", key, e)

        # Fallback in-memory
        _memory_cache[key] = (encoded, time.time() + ttl)

    @classmethod
    async def clear_pattern(cls, prefix: str) -> None:
        """Invalidate keys matching prefix."""
        try:
            client = await cls.get_client()
            if client:
                keys = await client.keys(f"{prefix}*")
                if keys:
                    await client.delete(*keys)
        except Exception as e:
            logger.debug("Redis clear error: %s", e)

        # In-memory clear
        for k in list(_memory_cache.keys()):
            if k.startswith(prefix):
                _memory_cache.pop(k, None)
