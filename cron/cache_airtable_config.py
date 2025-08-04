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
            
            # 1. Get dynamic variables data (existing functionality)
            dynamic_data = await webhook_service._get_customer_data_async(number)
            
            if dynamic_data:
                # Cache dynamic variables with phone number as key
                await redis_client.set(number, json.dumps(dynamic_data), ex=10800)
                logger.info(f"✅ Cached dynamic variables: {number}")
            else:
                logger.warning(f"⚠️ No dynamic variables found for: {number}")
            
            # 2. Get IVR configuration data (new functionality)
            from routes.ivr_routes import IVRService
            ivr_service = IVRService()
            
            # Force fresh Airtable lookup by bypassing cache
            logger.info(f"Force fresh Airtable lookup for IVR config: {number}")
            
            # Use ThreadPoolExecutor for sync method calls
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Temporarily disable Redis to force Airtable lookup
                import services.redis_client
                
                # Store the original function
                original_function = services.redis_client.is_redis_configured
                
                # Create a mock function that always returns False
                def mock_redis_disabled():
                    return False
                
                # Temporarily replace the function
                services.redis_client.is_redis_configured = mock_redis_disabled
                
                try:
                    ivr_config = executor.submit(ivr_service.get_ivr_configuration, number).result()
                finally:
                    # Restore the original function
                    services.redis_client.is_redis_configured = original_function
            
            if ivr_config:
                # Cache IVR config with ivr_config_ prefix
                cache_key = f"ivr_config_{number}"
                await redis_client.set(cache_key, json.dumps(ivr_config), ex=10800)
                logger.info(f"✅ Cached IVR config: {number}")
                
                # 3. Preload transfer numbers for all languages in IVR config
                if ivr_config.get('ivr_setup'):
                    # Multi-language setup - preload transfer numbers for all options
                    for option in ivr_config.get('options', []):
                        language_id = option.get('language_id')
                        if language_id:
                            # Create a new executor for each transfer number lookup
                            with concurrent.futures.ThreadPoolExecutor() as transfer_executor:
                                transfer_number = transfer_executor.submit(ivr_service.get_transfer_number, language_id).result()
                                if transfer_number:
                                    transfer_cache_key = f"transfer_number_{language_id}"
                                    await redis_client.set(transfer_cache_key, transfer_number, ex=10800)
                                    logger.info(f"✅ Cached transfer number for language {language_id}: {transfer_number}")
                else:
                    # Single language setup - preload transfer number for language_1
                    language_1_id = ivr_config.get('language_1_id')
                    if language_1_id:
                        # Create a new executor for transfer number lookup
                        with concurrent.futures.ThreadPoolExecutor() as transfer_executor:
                            transfer_number = transfer_executor.submit(ivr_service.get_transfer_number, language_1_id).result()
                            if transfer_number:
                                transfer_cache_key = f"transfer_number_{language_1_id}"
                                await redis_client.set(transfer_cache_key, transfer_number, ex=10800)
                                logger.info(f"✅ Cached transfer number for language {language_1_id}: {transfer_number}")
            else:
                logger.warning(f"⚠️ No IVR config found for: {number}")
            
            success_count += 1
                
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