-- Query to find unmatched intents that need new intent creation
-- Run this in Supabase SQL Editor to identify gaps in your intent database

SELECT 
    call_id,
    client_id,
    utterance,
    utterance_en,
    query_text,
    detected_lang,
    created_at,
    explanation
FROM call_reason_log 
WHERE unmatched_intent = true 
ORDER BY created_at DESC;

-- Alternative: Group by similar queries to identify patterns
SELECT 
    query_text,
    COUNT(*) as frequency,
    ARRAY_AGG(DISTINCT client_id) as clients,
    MIN(created_at) as first_seen,
    MAX(created_at) as last_seen
FROM call_reason_log 
WHERE unmatched_intent = true 
    AND query_text IS NOT NULL
GROUP BY query_text 
ORDER BY frequency DESC;

-- Find most common unmatched patterns (for intent creation)
SELECT 
    LOWER(TRIM(query_text)) as normalized_query,
    COUNT(*) as frequency,
    ARRAY_AGG(DISTINCT client_id) as affected_clients,
    MIN(created_at) as first_seen,
    MAX(created_at) as last_seen
FROM call_reason_log 
WHERE unmatched_intent = true 
    AND query_text IS NOT NULL
    AND LENGTH(TRIM(query_text)) > 10  -- Filter out very short queries
GROUP BY LOWER(TRIM(query_text))
HAVING COUNT(*) >= 2  -- Only show queries that appeared multiple times
ORDER BY frequency DESC, last_seen DESC;
