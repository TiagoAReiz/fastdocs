from redis.asyncio import from_url

from app.core.config import settings

redis_client = from_url(settings.REDIS_URL, decode_responses=True)
