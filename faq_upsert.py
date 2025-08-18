#!/usr/bin/env python3
"""
FAQ Upsert Script
Generates 1536-dim embeddings and upserts FAQ entries to Supabase
"""

from openai import OpenAI
from supabase import create_client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def vec_literal(arr):
    """Convert embedding array to PostgreSQL vector literal format"""
    return "[" + ",".join(str(x) for x in arr) + "]"

def upsert_faq(client_id, title, answer, locale="en", tags=None, metadata=None):
    """
    Upsert a FAQ entry with embedding
    
    Args:
        client_id (str): UUID of the client
        title (str): FAQ question/title
        answer (str): FAQ answer
        locale (str): Language locale (default: "en")
        tags (list): Optional tags for categorization
        metadata (dict): Optional metadata
    """
    # Initialize clients
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    
    # Generate embedding
    print(f"Generating embedding for: '{title}'")
    emb = openai_client.embeddings.create(
        model="text-embedding-3-small", 
        input=answer
    ).data[0].embedding
    
    # Convert to vector literal
    v = vec_literal(emb)
    
    # Prepare parameters
    params = {
        "p_client": client_id,
        "p_title": title,
        "p_answer": answer,
        "p_embedding": v,
        "p_locale": locale,
        "p_tags": tags or [],
        "p_metadata": metadata or {}
    }
    
    # Call RPC
    print(f"Upserting FAQ to Supabase...")
    result = sb.rpc("kb_upsert_faq", params).execute()
    
    if hasattr(result, 'error') and result.error:
        print(f"Error: {result.error}")
        return False
    else:
        print(f"Successfully upserted FAQ: '{title}'")
        return True

def main():
    """Example usage"""
    # Example FAQ entry
    client_id = "00000000-0000-0000-0000-000000000001"
    title = "Do you offer a warranty?"
    answer = "Yes—25-year performance and 12-year product. Extensions available."
    
    success = upsert_faq(
        client_id=client_id,
        title=title,
        answer=answer,
        locale="en",
        tags=["warranty", "general"],
        metadata={
            "source": "faq",
            "question": "Do you offer a warranty?"
        }
    )
    
    if success:
        print("FAQ upsert completed successfully!")
    else:
        print("FAQ upsert failed!")

if __name__ == "__main__":
    main()
