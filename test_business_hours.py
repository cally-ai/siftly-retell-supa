#!/usr/bin/env python3
"""
Test script for siftly_check_business_hours functionality
"""
import sys
import os
from datetime import datetime
import pytz

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.webhook_service import webhook_service
from utils.logger import get_logger

logger = get_logger(__name__)

def test_business_hours_check():
    """Test the business hours check functionality"""
    
    # Test data - simulate a function call from Retell AI
    test_data = {
        "name": "siftly_check_business_hours",
        "args": {
            "client_id": "recTestClient123"  # Replace with actual client ID for testing
        }
    }
    
    print("=== Testing Business Hours Check ===")
    print(f"Test data: {test_data}")
    
    try:
        # Test the business hours check
        result = webhook_service.process_business_hours_check(test_data)
        print(f"Result: {result}")
        
        # Test timezone conversion
        print("\n=== Testing Timezone Conversion ===")
        current_utc = datetime.utcnow()
        print(f"Current UTC: {current_utc}")
        
        # Test with a specific timezone
        test_timezone = "Europe/Amsterdam"
        try:
            tz = pytz.timezone(test_timezone)
            local_time = current_utc.replace(tzinfo=pytz.UTC).astimezone(tz)
            print(f"Local time ({test_timezone}): {local_time}")
            print(f"Weekday: {local_time.strftime('%A').lower()}")
            print(f"Time: {local_time.strftime('%H:%M')}")
        except Exception as e:
            print(f"Timezone error: {e}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_business_hours_check() 