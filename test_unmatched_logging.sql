-- Test query to verify the new columns exist and check recent activity
-- Run this in Supabase SQL Editor

-- 1. Check if the new columns exist
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns 
WHERE table_name = 'call_reason_log' 
  AND column_name IN ('unmatched_intent', 'top_k_results', 'query_text')
ORDER BY column_name;

-- 2. Check recent call logs (last 10)
SELECT 
    id,
    call_id,
    client_id,
    primary_intent_id,
    confidence,
    unmatched_intent,
    query_text,
    created_at
FROM call_reason_log 
ORDER BY created_at DESC 
LIMIT 10;

-- 3. Check if there are any unmatched intents yet
SELECT COUNT(*) as unmatched_count
FROM call_reason_log 
WHERE unmatched_intent = true;

-- 4. Check confidence distribution
SELECT 
    CASE 
        WHEN confidence = 0.0 THEN 'Zero (0.0)'
        WHEN confidence < 0.3 THEN 'Low (< 0.3)'
        WHEN confidence < 0.7 THEN 'Medium (0.3-0.7)'
        ELSE 'High (> 0.7)'
    END as confidence_level,
    COUNT(*) as count
FROM call_reason_log 
GROUP BY confidence_level
ORDER BY count DESC;
