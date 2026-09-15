-- Migration: Simplify Email Campaign Instance Statuses
-- Maps old status values to new simplified statuses
-- Old: pending, draft, ready, sent, skipped
-- New: scheduled, paused, sent
--
-- Run with: mysql -u username -p database < scripts/migrate_campaign_statuses.sql
-- Or via Railway: railway run mysql < scripts/migrate_campaign_statuses.sql

-- First, add the new ENUM values to the status column
-- Note: MySQL doesn't support IF NOT EXISTS for ENUM modification,
-- so we need to redefine the entire column
ALTER TABLE sdll_email_campaign_instances
MODIFY COLUMN status ENUM('pending', 'draft', 'ready', 'sent', 'skipped', 'scheduled', 'paused')
DEFAULT 'scheduled';

-- Map old statuses to new ones
-- pending/draft/ready -> scheduled (these are all "will send" states)
UPDATE sdll_email_campaign_instances
SET status = 'scheduled'
WHERE status IN ('pending', 'draft', 'ready');

-- skipped -> paused (these are "won't send" states)
UPDATE sdll_email_campaign_instances
SET status = 'paused'
WHERE status = 'skipped';

-- Verify the migration
SELECT status, COUNT(*) as count
FROM sdll_email_campaign_instances
GROUP BY status;
