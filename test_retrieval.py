#!/usr/bin/env python3
"""
Quick Retrieval Smoke Test
Tests semantic search end-to-end functionality
"""

from openai import OpenAI
from supabase import create_client
import os
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

def vec_literal(arr): 
    return "[" + ",".join(str(x) for x in arr) + "]"

def test_retrieval():
    """Test semantic search retrieval"""
    
    # Initialize clients
    oa = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    
    # Test query
    q = "What is your warranty?"
    print(f"Query: '{q}'")
    
    # Generate embedding
    print("Generating embedding...")
    emb = oa.embeddings.create(model="text-embedding-3-small", input=q).data[0].embedding
    v = vec_literal(emb)
    
    # Search
    print("Searching knowledge base...")
    res = sb.rpc("kb_search", {
        "p_client": "00000000-0000-0000-0000-000000000001",
        "p_query_embedding": v,
        "p_top_k": 5,
        "p_locale": "en"
    }).execute()
    
    # Display results
    print("\nSearch Results:")
    print("-" * 50)
    
    if hasattr(res, 'error') and res.error:
        print(f"Error: {res.error}")
        return False
    
    data = res.data or []
    print(f"Raw response data: {json.dumps(data, indent=2)}")
    
    if not data:
        print("No results found")
        return False
    
    for r in data:
        score = round(r["score"], 3)
        title = r["title"]
        print(f"{score} - {title}")
    
    print(f"\nFound {len(data)} results")
    return True

if __name__ == "__main__":
    print("=== Semantic Search Smoke Test ===")
    success = test_retrieval()
    
    if success:
        print("\n✅ Smoke test passed!")
    else:
        print("\n❌ Smoke test failed!")
