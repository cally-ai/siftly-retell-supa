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
from services.airtable_service import airtable_service
from utils.logger import get_logger
from pyairtable import Table
from config import Config

logger = get_logger(__name__)

async def discover_phone_numbers():
    """Automatically discover all phone numbers from Airtable"""
    try:
        # Query the Twilio number mapping table
        twilio_table = Table(Config.AIRTABLE_API_KEY, Config.AIRTABLE_BASE_ID, 'tbl0PeZoX2qgl74ZT')
        records = await asyncio.to_thread(twilio_table.all)
        
        phone_numbers = []
        for record in records:
            twilio_number = record['fields'].get('twilio_number', '')
            if twilio_number:
                phone_numbers.append(twilio_number)
                logger.info(f"Discovered phone number: {twilio_number}")
        
        logger.info(f"Auto-discovered {len(phone_numbers)} phone numbers from Airtable")
        return phone_numbers
        
    except Exception as e:
        logger.error(f"Error discovering phone numbers: {e}")
        # Fallback to hardcoded list
        fallback_numbers = [
            "+32460234291",  # Rasolar
        ]
        logger.info(f"Using fallback list: {fallback_numbers}")
        return fallback_numbers

async def preload_cache():
    """Preload Airtable configurations into Redis cache"""
    if not is_redis_configured():
        logger.error("Redis not configured - cannot preload cache")
        return
    
    # Auto-discover phone numbers
    to_numbers = await discover_phone_numbers()
    
    if not to_numbers:
        logger.warning("No phone numbers found to cache")
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