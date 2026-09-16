-- Add detailed event information columns to sdll_assignr_webhook_events
-- These columns store parsed information from webhook processing

-- Official name (who performed the action)
ALTER TABLE sdll_assignr_webhook_events ADD COLUMN official_name VARCHAR(100) DEFAULT NULL;

-- Action type (accepted, declined, assigned, removed)
ALTER TABLE sdll_assignr_webhook_events ADD COLUMN action_type VARCHAR(50) DEFAULT NULL;

-- Position (Plate, Base, etc.)
ALTER TABLE sdll_assignr_webhook_events ADD COLUMN position VARCHAR(50) DEFAULT NULL;

-- Event timestamp from Assignr payload (local time when event occurred)
ALTER TABLE sdll_assignr_webhook_events ADD COLUMN event_timestamp DATETIME DEFAULT NULL;
