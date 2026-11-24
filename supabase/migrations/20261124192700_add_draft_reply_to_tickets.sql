-- Add draft_reply column to tickets table for Human-In-The-Loop review
ALTER TABLE tickets 
ADD COLUMN IF NOT EXISTS draft_reply text;
