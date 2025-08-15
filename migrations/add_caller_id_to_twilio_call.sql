-- Migration: Add caller_id to twilio_call table
-- This allows linking twilio_call records to caller records for customer tracking

-- Add caller_id column to twilio_call table
ALTER TABLE public.twilio_call 
ADD COLUMN caller_id uuid;

-- Add foreign key constraint to link to caller table
ALTER TABLE public.twilio_call 
ADD CONSTRAINT twilio_call_caller_id_fkey 
FOREIGN KEY (caller_id) REFERENCES public.caller(id);

-- Add index for better query performance
CREATE INDEX idx_twilio_call_caller_id ON public.twilio_call(caller_id);

-- Add comment for documentation
COMMENT ON COLUMN public.twilio_call.caller_id IS 'Foreign key to caller table for customer tracking';
