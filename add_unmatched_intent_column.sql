-- Migration: Add unmatched_intent column to call_reason_log table
-- Run this in Supabase SQL Editor

-- Add the unmatched_intent column
ALTER TABLE call_reason_log 
ADD COLUMN unmatched_intent BOOLEAN DEFAULT FALSE;

-- Add the top_k_results column for storing vector search results
ALTER TABLE call_reason_log 
ADD COLUMN top_k_results JSONB;

-- Add the query_text column for storing the query that failed to match
ALTER TABLE call_reason_log 
ADD COLUMN query_text TEXT;

-- Create an index for better query performance on unmatched intents
CREATE INDEX idx_call_reason_log_unmatched_intent 
ON call_reason_log(unmatched_intent) 
WHERE unmatched_intent = true;

-- Create an index for querying by query_text
CREATE INDEX idx_call_reason_log_query_text 
ON call_reason_log(query_text) 
WHERE query_text IS NOT NULL;

-- Update existing records to have unmatched_intent = false
UPDATE call_reason_log 
SET unmatched_intent = false 
WHERE unmatched_intent IS NULL;
