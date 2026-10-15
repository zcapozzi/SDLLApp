-- Migration: Add contact_preferences table for SMS/email opt-in/opt-out tracking
--
-- This table supports:
-- - Multiple channels (sms, email)
-- - Multiple message categories (rainout, postgame, schedule_change, etc.)
-- - Per-contact preferences with toggle history
-- - One contact can have multiple records (one per category/channel combo)

CREATE TABLE IF NOT EXISTS sdll_contact_preferences (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Organization context (for multi-org support)
    org_id BIGINT NOT NULL DEFAULT 1,

    -- Optional link to registered user
    user_id BIGINT NULL,

    -- Contact info: phone in E.164 format (+19195551234) or email
    contact_value VARCHAR(255) NOT NULL,

    -- Channel type
    contact_type ENUM('sms', 'email') NOT NULL,

    -- Message category this preference applies to
    -- rainout, postgame, schedule_change, game_reminder, weekly_digest, general
    message_category VARCHAR(50) NOT NULL,

    -- Current opt-in status: 1 = opted in, 0 = opted out
    opted_in TINYINT(1) NOT NULL DEFAULT 1,

    -- Timestamps for tracking preference changes
    opted_in_at DATETIME NULL,
    opted_out_at DATETIME NULL,

    -- Audit timestamps
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- Source of the preference change
    -- e.g., 'registration_form', 'sms_stop', 'sms_start', 'web_settings', 'admin', 'import'
    source VARCHAR(50) NULL,

    -- Foreign key to users (optional)
    CONSTRAINT fk_contact_pref_user FOREIGN KEY (user_id)
        REFERENCES sdll_users(ID) ON DELETE SET NULL,

    -- Unique constraint: one record per contact/channel/category combo
    UNIQUE KEY unique_contact_channel_category (contact_value, contact_type, message_category, org_id),

    -- Indexes for common queries
    INDEX idx_contact_type_category (contact_type, message_category, opted_in),
    INDEX idx_user_id (user_id),
    INDEX idx_org_id (org_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Example usage:
--
-- Check if phone is opted in for rainout texts:
-- SELECT opted_in FROM sdll_contact_preferences
-- WHERE contact_value = '+19195551234'
--   AND contact_type = 'sms'
--   AND message_category = 'rainout';
--
-- Get all phones opted OUT of postgame texts (to filter before sending):
-- SELECT contact_value FROM sdll_contact_preferences
-- WHERE contact_type = 'sms'
--   AND message_category = 'postgame'
--   AND opted_in = 0;
--
-- Handle STOP message (opt out of all SMS):
-- UPDATE sdll_contact_preferences
-- SET opted_in = 0, opted_out_at = NOW(), source = 'sms_stop'
-- WHERE contact_value = '+19195551234' AND contact_type = 'sms';
