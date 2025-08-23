#!/usr/bin/env python3
"""
Check what embeddings exist in the database
"""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not all([SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY]):
    print("ERROR: Missing required environment variables")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def main():
    print("Checking embeddings in database...")
    
    # Get all embeddings
    result = supabase.table("intent_embedding").select("client_id,intent_id").execute()
    if hasattr(result, "error") and result.error:
        print(f"ERROR fetching embeddings: {result.error}")
        return
    
    embeddings = result.data or []
    print(f"Total embeddings: {len(embeddings)}")
    
    # Group by client
    by_client = {}
    for emb in embeddings:
        client_id = emb["client_id"]
        by_client.setdefault(client_id, []).append(emb["intent_id"])
    
    print(f"\nEmbeddings by client:")
    for client_id, intent_ids in by_client.items():
        print(f"  {client_id}: {len(intent_ids)} embeddings")
        if len(intent_ids) <= 5:
            print(f"    Intent IDs: {intent_ids}")
        else:
            print(f"    Intent IDs: {intent_ids[:3]}... and {len(intent_ids)-3} more")
    
    # Check specific client
    target_client = "94ec6461-9466-44f2-9938-9e9a3e60ab39"
    if target_client in by_client:
        print(f"\n✅ Target client {target_client} has {len(by_client[target_client])} embeddings")
    else:
        print(f"\n❌ Target client {target_client} has NO embeddings")

if __name__ == "__main__":
    main()
