-- Query to find unmatched intents that need new intent creation
-- Run this in Supabase SQL Editor to identify gaps in your intent database

-- IMPORTANT: First run the migration in add_unmatched_intent_column.sql
-- Then you can use these queries:

-- 1. Recent unmatched intents (requires migration)
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

-- 2. Alternative: Find intents with very low confidence (works without migration)
SELECT 
    call_id,
    client_id,
    utterance,
    utterance_en,
    detected_lang,
    created_at,
    explanation,
    confidence,
    embedding_top1_sim
FROM call_reason_log 
WHERE confidence < 0.3  -- Very low confidence might indicate unmatched intents
    AND embedding_top1_sim < 0.5  -- Low similarity scores
ORDER BY created_at DESC;

-- 3. Find calls with no primary_intent_id (works without migration)
SELECT 
    call_id,
    client_id,
    utterance,
    utterance_en,
    detected_lang,
    created_at,
    explanation
FROM call_reason_log 
WHERE primary_intent_id IS NULL 
    OR primary_intent_id = ''
ORDER BY created_at DESC;

-- 4. Group by similar queries to identify patterns (requires migration)
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

-- 5. Find most common unmatched patterns (requires migration)
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

-- 6. Alternative: Find patterns in low-confidence calls (works without migration)
SELECT 
    LOWER(TRIM(utterance)) as normalized_utterance,
    COUNT(*) as frequency,
    ARRAY_AGG(DISTINCT client_id) as affected_clients,
    AVG(confidence) as avg_confidence,
    MIN(created_at) as first_seen,
    MAX(created_at) as last_seen
FROM call_reason_log 
WHERE confidence < 0.3 
    AND utterance IS NOT NULL
    AND LENGTH(TRIM(utterance)) > 10
GROUP BY LOWER(TRIM(utterance))
HAVING COUNT(*) >= 2
ORDER BY frequency DESC, last_seen DESC;
