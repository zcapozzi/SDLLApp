-- Migration: Add notification drafts table and link to notification queue
-- Run with: mysql -u user -p database < scripts/add_notification_drafts.sql

-- Create notification drafts table
CREATE TABLE IF NOT EXISTS sdll_notification_drafts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Recipient info
    recipient_email VARCHAR(255) NOT NULL,
    recipient_name VARCHAR(100),
    recipient_type ENUM('admin', 'coach', 'umpire', 'parent', 'partner') NOT NULL,

    -- CC recipients (JSON array)
    cc_emails JSON,

    -- Editable email content
    subject VARCHAR(255) NOT NULL,
    body_text TEXT NOT NULL,
    body_html TEXT,

    -- Status
    status ENUM('draft', 'sent', 'deleted') NOT NULL DEFAULT 'draft',
    sent_at DATETIME,

    -- Flag for whether content has been manually edited
    auto_generated SMALLINT DEFAULT 1,

    -- Indexes
    INDEX idx_status (status),
    INDEX idx_recipient_type (recipient_type),
    INDEX idx_recipient_email (recipient_email)
);

-- Add draft_id column to notification queue
ALTER TABLE sdll_notification_queue
ADD COLUMN draft_id INT,
ADD CONSTRAINT fk_notification_draft
    FOREIGN KEY (draft_id)
    REFERENCES sdll_notification_drafts(id)
    ON DELETE SET NULL;

-- Index for faster lookups
CREATE INDEX idx_notification_queue_draft ON sdll_notification_queue(draft_id);
