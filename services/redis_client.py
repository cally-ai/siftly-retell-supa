"""
Redis client service for caching Airtable configurations
"""
import redis.asyncio as redis
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

# Redis URL from environment or config
REDIS_URL = getattr(Config, 'REDIS_URL', None)

if REDIS_URL:
    try:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        logger.info("Redis client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Redis client: {e}")
        redis_client = None
else:
    logger.warning("REDIS_URL not configured - caching disabled")
    redis_client = None

def is_redis_configured() -> bool:
    """Check if Redis is properly configured"""
    return redis_client is not None 