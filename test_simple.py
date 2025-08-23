#!/usr/bin/env python3
"""
Simple test to check basic endpoint functionality
"""

import requests
import json

# Simple test data
test_data = {
    "call": {
        "transcript": "Hello, I need help",
        "call_id": "test_1",
        "retell_llm_dynamic_variables": { "client_id": "94ec6461-9466-44f2-9938-9e9a3e60ab39" }
    }
}

url = "https://siftly-retell-supa.onrender.com/classify-intent"

print(f"Testing {url}")
print(f"Data: {json.dumps(test_data, indent=2)}")

try:
    response = requests.post(
        url,
        json=test_data,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f"Error: {e}")
