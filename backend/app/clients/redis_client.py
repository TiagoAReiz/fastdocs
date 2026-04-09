import json
import time
from uuid import UUID

from app.core.redis import redis_client


# --- Cache ---

async def cache_get(key: str) -> dict | None:
    data = await redis_client.get(key)
    if data is None:
        return None
    return json.loads(data)


async def cache_set(key: str, value: dict, ttl: int = 1800) -> None:
    await redis_client.set(key, json.dumps(value), ex=ttl)


async def cache_delete(key: str) -> None:
    await redis_client.delete(key)


async def cache_invalidate_tenant(tenant_id: UUID) -> None:
    pattern = f"cache:query:{tenant_id}:*"
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
        if keys:
            await redis_client.delete(*keys)
        if cursor == 0:
            break


# --- Rate Limiting (Sliding Window) ---

async def rate_limit_check(
    key: str, limit: int, window: int
) -> tuple[bool, dict]:
    now = time.time()
    window_start = now - window

    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, window)
    results = await pipe.execute()

    count = results[2]
    remaining = max(0, limit - count)
    allowed = count <= limit

    headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(int(now + window)),
    }

    return allowed, headers
