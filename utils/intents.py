#!/usr/bin/env python3
"""
Intent utility functions for per-client slug resolution
"""

from functools import lru_cache
from typing import Optional
from supabase import Client

@lru_cache(maxsize=2048)
def get_intent_id_by_slug(sb: Client, client_id: str, slug: str) -> Optional[str]:
    """
    Get intent ID by client and slug with caching.
    
    Args:
        sb: Supabase client
        client_id: Client UUID
        slug: Intent slug (e.g., "general_question")
        
    Returns:
        Intent UUID or None if not found
    """
    try:
        r = sb.table("intent").select("id").eq("client_id", client_id).eq("slug", slug).single().execute()
        if hasattr(r, "error") and r.error:
            # Optionally auto-provision general question intent
            if slug == "general_question":
                res = sb.rpc("ensure_general_question", {"p_client": client_id}).execute()
                if hasattr(res, "error") and res.error:
                    print(f"Failed to auto-provision general question for client {client_id}: {res.error}")
                    return None
                return res.data  # UUID
            return None
        return r.data["id"]
    except Exception as e:
        print(f"Error looking up intent by slug {slug} for client {client_id}: {e}")
        return None

def get_general_question_intent_id(sb: Client, client_id: str) -> Optional[str]:
    """
    Get the General Question intent ID for a specific client.
    
    Args:
        sb: Supabase client
        client_id: Client UUID
        
    Returns:
        General Question intent UUID or None if not found
    """
    return get_intent_id_by_slug(sb, client_id, "general_question")
