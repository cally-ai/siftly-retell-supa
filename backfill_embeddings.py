#!/usr/bin/env python3
"""
Backfill Embeddings Script for Siftly Retell Supabase

This script efficiently backfills embeddings for intent examples in your Supabase database.
It processes intent examples in batches and generates embeddings using OpenAI.

Usage:
    python backfill_embeddings.py

Environment Variables Required:
    - SUPABASE_URL
    - SUPABASE_SERVICE_ROLE_KEY
    - OPENAI_API_KEY

Optional Environment Variables:
    - BATCH_SIZE (default: 100)
    - EMBED_MODEL (default: text-embedding-3-small)
"""

import os
import time
import math
from typing import List
from dotenv import load_dotenv
from supabase import create_client
from openai import OpenAI
from openai import APIError, RateLimitError

# Load environment variables from .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "<YOUR_SUPABASE_URL>")
SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "<YOUR_SERVICE_ROLE_KEY>")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "<YOUR_OPENAI_API_KEY>")

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))   # tune as you wish (50–200 is fine)
MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
MAX_RETRIES = 5

sb = create_client(SUPABASE_URL, SERVICE_ROLE_KEY)
ai = OpenAI(api_key=OPENAI_API_KEY)

def fetch_missing(limit: int):
    """Grab another batch of rows missing embeddings"""
    resp = sb.table("intent_example") \
        .select("id,text") \
        .is_("embedding", "null") \
        .limit(limit) \
        .execute()
    if getattr(resp, "error", None):
        raise RuntimeError(resp.error.message)
    return resp.data or []

def embed_batch(texts: List[str]):
    """Handle rate-limits with exponential backoff"""
    delay = 2.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return ai.embeddings.create(model=MODEL, input=texts)
        except (RateLimitError, APIError) as e:
            if attempt == MAX_RETRIES:
                raise
            print(f"Rate limited, retrying in {delay}s... (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(delay)
            delay = min(delay * 2, 30.0)

def update_embedding(row_id: str, vec: List[float]):
    """Update a single row with its embedding"""
    resp = sb.table("intent_example").update({"embedding": vec}).eq("id", row_id).execute()
    if getattr(resp, "error", None):
        raise RuntimeError(resp.error.message)

def count_missing():
    """Count how many rows are missing embeddings"""
    resp = sb.table("intent_example").select("id", count="exact").is_("embedding", "null").execute()
    if getattr(resp, "error", None):
        raise RuntimeError(resp.error.message)
    return resp.count or 0

def main():
    """Main function to process all missing embeddings"""
    print(f"🚀 Starting embedding backfill with batch size {BATCH_SIZE}")
    print(f"📊 Model: {MODEL}")
    
    # Check initial count
    initial_missing = count_missing()
    print(f"📈 Found {initial_missing} rows missing embeddings")
    
    if initial_missing == 0:
        print("✅ No missing embeddings found!")
        return
    
    total_updated = 0
    batch_count = 0
    
    while True:
        batch = fetch_missing(BATCH_SIZE)
        if not batch:
            print(f"✅ Done. Updated {total_updated} rows total.")
            break

        batch_count += 1
        print(f"\n🔄 Processing batch {batch_count} ({len(batch)} rows)...")

        texts = [r["text"] or "" for r in batch]
        emb_resp = embed_batch(texts)
        data = emb_resp.data
        
        if len(data) != len(batch):
            raise RuntimeError(f"Embedding count mismatch: got {len(data)} for {len(batch)} rows")

        # Update all rows in this batch
        for r, e in zip(batch, data):
            update_embedding(r["id"], e.embedding)

        total_updated += len(batch)
        remaining = count_missing()
        
        print(f"✔ Updated {len(batch)} rows in this batch")
        print(f"📊 Progress: {total_updated} total updated, {remaining} remaining")
        
        # Small pause to be nice to both APIs
        time.sleep(0.3)

if __name__ == "__main__":
    assert SUPABASE_URL and SERVICE_ROLE_KEY and OPENAI_API_KEY, "Set SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, OPENAI_API_KEY"
    main()
