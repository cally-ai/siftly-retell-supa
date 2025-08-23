#!/usr/bin/env python3
"""
Script to populate intent_embedding table with embeddings for existing intents.
Run this once to set up the local vector index.
"""

import os
import sys
import math
import random
import time
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not all([OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY]):
    print("ERROR: Missing required environment variables")
    sys.exit(1)

# Initialize clients
openai_client = OpenAI(api_key=OPENAI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def l2_normalize(v):
    """L2-normalize a vector"""
    n = math.sqrt(sum(x*x for x in v)) or 1.0
    return [x / n for x in v]

def get_intent_text(intent):
    """Generate text for embedding from intent data"""
    parts = []
    if intent.get("name"):
        parts.append(intent["name"])
    if intent.get("description"):
        parts.append(intent["description"])
    return " ".join(parts).strip()

def main():
    print("Fetching all intents from database...")
    
    # Get all intents
    result = supabase.table("intent").select("id,client_id,name,description").execute()
    if hasattr(result, "error") and result.error:
        print(f"ERROR fetching intents: {result.error}")
        return
    
    intents = result.data or []
    print(f"Found {len(intents)} intents")
    
    if not intents:
        print("No intents found. Exiting.")
        return
    
    # Check which intents already have embeddings
    existing_result = supabase.table("intent_embedding").select("intent_id").execute()
    if hasattr(existing_result, "error") and existing_result.error:
        print(f"ERROR checking existing embeddings: {existing_result.error}")
        return
    
    existing_intent_ids = {row["intent_id"] for row in (existing_result.data or [])}
    
    # Filter intents that need embeddings
    intents_to_process = [intent for intent in intents if intent["id"] not in existing_intent_ids]
    
    if not intents_to_process:
        print("All intents already have embeddings. Exiting.")
        return
    
    print(f"Processing {len(intents_to_process)} intents that need embeddings...")
    
    success_count = 0
    error_count = 0
    
    for i, intent in enumerate(intents_to_process, 1):
        try:
            # Generate text for embedding
            intent_text = get_intent_text(intent)
            if not intent_text:
                print(f"SKIP intent {intent['id']}: no text to embed")
                continue
            
            print(f"[{i}/{len(intents_to_process)}] Processing intent: {intent['name']}")
            
            # Generate embedding
            embedding_response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=intent_text
            )
            embedding = embedding_response.data[0].embedding
            
            # Normalize embedding
            embedding = l2_normalize(embedding)
            
            # Insert into database
            supabase.table("intent_embedding").upsert({
                "client_id": intent["client_id"],
                "intent_id": intent["id"],
                "embedding": embedding,  # Pass list directly
                "updated_at": "now()"
            }).execute()
            
            success_count += 1
            print(f"  ✓ Success")
            
        except Exception as e:
            error_count += 1
            print(f"  ✗ ERROR: {e}")
    
    print(f"\n=== SUMMARY ===")
    print(f"Total intents: {len(intents)}")
    print(f"Already had embeddings: {len(existing_intent_ids)}")
    print(f"Processed: {len(intents_to_process)}")
    print(f"Success: {success_count}")
    print(f"Errors: {error_count}")
    
    if success_count > 0:
        print(f"\n✅ Successfully populated {success_count} intent embeddings!")
        print("Your local vector index will now be much faster!")

if __name__ == "__main__":
    main()
