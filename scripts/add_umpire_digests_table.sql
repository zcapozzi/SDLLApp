-- Migration: Add sdll_umpire_digests table for Academy umpire weekly digests
-- Run this on production database

CREATE TABLE IF NOT EXISTS sdll_umpire_digests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Targeting - identify umpire by Assignr ID
    assignr_official_id INT NOT NULL,
    umpire_name VARCHAR(200) NOT NULL,
    week_start DATE NOT NULL,
    year INT NOT NULL,
    is_spring SMALLINT NOT NULL,

    -- Optional link to local profile
    umpire_profile_id INT,

    -- Recipients (JSON array of email addresses - umpire + parents)
    recipient_emails TEXT NOT NULL,

    -- Content
    subject VARCHAR(255) NOT NULL,
    body_html TEXT NOT NULL,
    game_count INT NOT NULL DEFAULT 0,

    -- Workflow
    status ENUM('draft', 'ready', 'sent', 'skipped') NOT NULL DEFAULT 'draft',
    sent_at DATETIME,
    sent_by BIGINT,

    -- Foreign keys
    FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id) ON DELETE SET NULL,
    FOREIGN KEY (sent_by) REFERENCES sdll_users(ID) ON DELETE SET NULL,

    -- Unique constraint: one digest per umpire per week
    UNIQUE KEY uq_umpire_digest_official_week (assignr_official_id, week_start),

    -- Indexes
    INDEX idx_umpire_digest_week (week_start),
    INDEX idx_umpire_digest_status (status),
    INDEX idx_umpire_digest_season (year, is_spring)
);
