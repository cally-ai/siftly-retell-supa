#!/usr/bin/env python3
"""
Test script for Redis caching functionality
"""
import asyncio
import json
import sys
import os

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.redis_client import redis_client, is_redis_configured
from utils.logger import get_logger

logger = get_logger(__name__)

async def test_redis_cache():
    """Test Redis cache functionality"""
    if not is_redis_configured():
        logger.error("Redis not configured - cannot test cache")
        return False
    
    test_number = "+32460234291"
    test_data = {
        "customer_name": "Test Customer",
        "preferred_language": "Dutch",
        "test_field": "test_value"
    }
    
    try:
        # Test 1: Set cache
        logger.info(f"Testing cache set for {test_number}")
        await redis_client.set(test_number, json.dumps(test_data), ex=300)  # 5 minutes TTL
        logger.info("✅ Cache set successful")
        
        # Test 2: Get cache
        logger.info(f"Testing cache get for {test_number}")
        cached_data = await redis_client.get(test_number)
        if cached_data:
            retrieved_data = json.loads(cached_data)
            logger.info(f"✅ Cache get successful: {retrieved_data}")
            
            # Test 3: Verify data integrity
            if retrieved_data == test_data:
                logger.info("✅ Data integrity verified")
                return True
            else:
                logger.error("❌ Data integrity check failed")
                return False
        else:
            logger.error("❌ Cache get failed - no data retrieved")
            return False
            
    except Exception as e:
        logger.error(f"❌ Redis test failed: {e}")
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(test_redis_cache())
        if success:
            logger.info("🎉 Redis cache test passed!")
            sys.exit(0)
        else:
            logger.error("💥 Redis cache test failed!")
            sys.exit(1)
    except Exception as e:
        logger.error(f"💥 Redis test crashed: {e}")
        sys.exit(1) 