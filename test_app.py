#!/usr/bin/env python3
"""
Test script for the Siftly Retell AI webhook handler
"""

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
BASE_URL = "http://localhost:5000"  # Change this to your deployed URL

def test_health_endpoint():
    """Test the health check endpoint"""
    print("Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_retell_webhook():
    """Test the Retell AI webhook endpoint"""
    print("\nTesting Retell AI webhook endpoint...")
    
    # Sample webhook data
    webhook_data = {
        "event_type": "call_ended",
        "call_id": "test_call_123",
        "agent_id": "test_agent_456",
        "customer_id": "test_customer_789",
        "status": "completed",
        "transcript": "Hello, this is a test call. I need help with my account.",
        "summary": "Customer requested account assistance",
        "sentiment": "neutral",
        "duration": 180,
        "cost": 0.75
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/webhook/retell",
            json=webhook_data,
            headers={"Content-Type": "application/json"}
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_airtable_endpoints():
    """Test Airtable endpoints"""
    print("\nTesting Airtable endpoints...")
    
    # Test GET records
    try:
        response = requests.get(f"{BASE_URL}/airtable/records")
        print(f"GET Records - Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Records count: {data.get('count', 0)}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error testing GET records: {e}")
    
    # Test POST record
    test_record = {
        "Test Field": "Test Value",
        "Another Field": "Another Value",
        "Number Field": 42
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/airtable/records",
            json=test_record,
            headers={"Content-Type": "application/json"}
        )
        print(f"POST Record - Status Code: {response.status_code}")
        if response.status_code == 201:
            print("Record created successfully")
            record_data = response.json()
            record_id = record_data.get('record', {}).get('id')
            if record_id:
                print(f"Created record ID: {record_id}")
                
                # Test PUT record
                update_data = {"Test Field": "Updated Value"}
                response = requests.put(
                    f"{BASE_URL}/airtable/records/{record_id}",
                    json=update_data,
                    headers={"Content-Type": "application/json"}
                )
                print(f"PUT Record - Status Code: {response.status_code}")
                
                # Test DELETE record
                response = requests.delete(f"{BASE_URL}/airtable/records/{record_id}")
                print(f"DELETE Record - Status Code: {response.status_code}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error testing POST record: {e}")

def test_webhook_statistics():
    """Test webhook statistics endpoint"""
    print("\nTesting webhook statistics endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/webhook/statistics?hours=24")
        print(f"Statistics - Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Statistics: {json.dumps(data.get('statistics', {}), indent=2)}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error testing statistics: {e}")

def test_system_status():
    """Test system status endpoint"""
    print("\nTesting system status endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/status")
        print(f"Status - Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"System Status: {json.dumps(data, indent=2)}")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error testing status: {e}")

def main():
    """Run all tests"""
    print("=== Siftly Retell AI Webhook Handler - Test Suite ===\n")
    
    # Check if environment variables are set
    airtable_key = os.getenv('AIRTABLE_API_KEY')
    airtable_base = os.getenv('AIRTABLE_BASE_ID')
    
    print(f"Airtable API Key configured: {'Yes' if airtable_key else 'No'}")
    print(f"Airtable Base ID configured: {'Yes' if airtable_base else 'No'}")
    print()
    
    # Run tests
    tests = [
        ("Health Endpoint", test_health_endpoint),
        ("System Status", test_system_status),
        ("Retell Webhook", test_retell_webhook),
        ("Webhook Statistics", test_webhook_statistics),
        ("Airtable Endpoints", test_airtable_endpoints)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"Running {test_name} test...")
        result = test_func()
        results.append((test_name, result))
        print()
    
    # Summary
    print("=== Test Summary ===")
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
    
    all_passed = all(result for _, result in results)
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")

if __name__ == "__main__":
    main() 