-- Migration: Fix incorrect column types in retell_event table
-- The to_number and direction columns should be text, not timestamp with time zone

-- First, drop the existing columns (if they exist)
ALTER TABLE public.retell_event 
DROP COLUMN IF EXISTS to_number;

ALTER TABLE public.retell_event 
DROP COLUMN IF EXISTS direction;

-- Add the columns back with correct data types
ALTER TABLE public.retell_event 
ADD COLUMN to_number text;

ALTER TABLE public.retell_event 
ADD COLUMN direction text;

-- Add comments for documentation
COMMENT ON COLUMN public.retell_event.to_number IS 'Phone number being called (text format)';
COMMENT ON COLUMN public.retell_event.direction IS 'Call direction (inbound/outbound)';
