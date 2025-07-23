#!/usr/bin/env python3
"""
Cron job to preload Airtable configurations into Redis cache
Runs every 3 hours to keep cache fresh
"""
import asyncio
import json
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.webhook_service import webhook_service
from services.redis_client import redis_client, is_redis_configured
from utils.logger import get_logger

logger = get_logger(__name__)

# List of to_numbers to preload (you can automate this too)
to_numbers = [
    "+32460234291",  # Rasolar
    # Add more numbers as needed
]

async def preload_cache():
    """Preload Airtable configurations into Redis cache"""
    if not is_redis_configured():
        logger.error("Redis not configured - cannot preload cache")
        return
    
    logger.info(f"Starting cache preload for {len(to_numbers)} numbers")
    
    success_count = 0
    error_count = 0
    
    for number in to_numbers:
        try:
            logger.info(f"Preloading cache for: {number}")
            
            # Get data from Airtable
            data = await webhook_service._get_customer_data_async(number)
            
            if data:
                # Cache in Redis with 3-hour TTL
                await redis_client.set(number, json.dumps(data), ex=10800)
                logger.info(f"✅ Cached: {number}")
                success_count += 1
            else:
                logger.warning(f"⚠️ No data found for: {number}")
                error_count += 1
                
        except Exception as e:
            logger.error(f"❌ Error caching {number}: {e}")
            error_count += 1
    
    logger.info(f"Cache preload complete: {success_count} successful, {error_count} errors")

if __name__ == "__main__":
    try:
        asyncio.run(preload_cache())
        logger.info("Cron job completed successfully")
    except Exception as e:
        logger.error(f"Cron job failed: {e}")
        sys.exit(1) 