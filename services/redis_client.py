"""
Redis client service for caching Airtable configurations
"""
import redis.asyncio as redis
import redis as redis_sync
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

# Redis URL from environment or config
REDIS_URL = getattr(Config, 'REDIS_URL', None)

if REDIS_URL:
    try:
        # Async Redis client for async operations
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        # Sync Redis client for sync operations
        redis_client_sync = redis_sync.from_url(REDIS_URL, decode_responses=True)
        logger.info("Redis client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Redis client: {e}")
        redis_client = None
        redis_client_sync = None
else:
    logger.warning("REDIS_URL not configured - caching disabled")
    redis_client = None
    redis_client_sync = None

def is_redis_configured() -> bool:
    """Check if Redis is properly configured"""
    return redis_client is not None and redis_client_sync is not None 