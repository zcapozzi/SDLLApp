-- Migration: Add scheduling fields to day-of umpire notifications
-- This enables auto-send workflow with 15-minute review period

-- Add 'scheduled' to the status enum
ALTER TABLE sdll_umpire_dayof_notifications
MODIFY COLUMN status ENUM('draft', 'scheduled', 'sent', 'skipped') NOT NULL DEFAULT 'scheduled';

-- Add scheduling timestamp
ALTER TABLE sdll_umpire_dayof_notifications
ADD COLUMN scheduled_send_at DATETIME DEFAULT NULL AFTER sent_by;

-- Add deactivation fields
ALTER TABLE sdll_umpire_dayof_notifications
ADD COLUMN deactivated TINYINT(1) NOT NULL DEFAULT 0 AFTER scheduled_send_at;

ALTER TABLE sdll_umpire_dayof_notifications
ADD COLUMN deactivated_at DATETIME DEFAULT NULL AFTER deactivated;

ALTER TABLE sdll_umpire_dayof_notifications
ADD COLUMN deactivated_reason VARCHAR(50) DEFAULT NULL AFTER deactivated_at;

-- Add index for efficient cron queries
CREATE INDEX idx_dayof_scheduled_send ON sdll_umpire_dayof_notifications(status, deactivated, scheduled_send_at);

-- Migrate existing draft notifications to scheduled (optional - run if needed)
-- UPDATE sdll_umpire_dayof_notifications
-- SET status = 'scheduled', scheduled_send_at = DATE_ADD(created_at, INTERVAL 15 MINUTE)
-- WHERE status = 'draft';
