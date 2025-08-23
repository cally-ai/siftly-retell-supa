#!/usr/bin/env python3
"""
Test script to debug vector index status
"""

import requests
import json

client_id = "94ec6461-9466-44f2-9938-9e9a3e60ab39"
base_url = "https://siftly-retell-supa.onrender.com"

# Test 1: Check index stats
print("=== Testing Index Stats ===")
try:
    response = requests.get(f"{base_url}/index-stats/{client_id}")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Testing Intent Classification ===")
# Test 2: Intent classification
test_data = {
    "call": {
        "transcript": "I need to book an appointment for a site survey",
        "call_id": "debug_test",
        "retell_llm_dynamic_variables": { "client_id": client_id }
    }
}

try:
    response = requests.post(
        f"{base_url}/classify-intent",
        json=test_data,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        telemetry = result.get("telemetry", {})
        
        print(f"Intent: {result.get('intent_name')}")
        print(f"Confidence: {result.get('confidence')}")
        print(f"Needs clarification: {result.get('needs_clarification')}")
        
        print(f"\nFull Telemetry:")
        print(json.dumps(telemetry, indent=2))
        
        # Check if we can infer which path was taken
        if telemetry.get('ann_ms', 0) > 100:
            print("🔍 High ANN time suggests fallback to Supabase RPC")
        else:
            print("⚡ Low ANN time suggests HNSW vector index")
            
    else:
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"Error: {e}")

print("\n=== Test Complete ===")
