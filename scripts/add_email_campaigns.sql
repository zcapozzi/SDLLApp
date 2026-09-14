-- Email Campaign System Migration
-- Run with: mysql --force sdll < scripts/add_email_campaigns.sql
-- Using --force to continue on errors (e.g., if tables already exist)

-- ============================================================================
-- Table 1: Email Campaign Templates
-- Stores reusable templates with variable placeholders
-- ============================================================================

CREATE TABLE IF NOT EXISTS sdll_email_campaign_templates (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    category VARCHAR(50) NOT NULL,

    -- Template content (with {{variable}} placeholders)
    subject_template VARCHAR(255) NOT NULL,
    body_html_template TEXT NOT NULL,
    body_text_template TEXT,

    -- Trigger settings
    trigger_type ENUM('milestone', 'manual') DEFAULT 'milestone',
    trigger_milestone VARCHAR(50),
    trigger_days_offset INT DEFAULT 0,

    -- Audience targeting
    recipient_type VARCHAR(50) NOT NULL,
    recipient_status_filter VARCHAR(100),

    active TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- Table 2: Campaign Instances
-- Generated per-season with editable drafts
-- ============================================================================

CREATE TABLE IF NOT EXISTS sdll_email_campaign_instances (
    id INT PRIMARY KEY AUTO_INCREMENT,
    template_id INT NOT NULL,
    org_season_id BIGINT NOT NULL,

    trigger_date DATE NOT NULL,
    trigger_date_override TINYINT DEFAULT 0,

    -- Editable content (variables injected)
    subject VARCHAR(255) NOT NULL,
    body_html TEXT NOT NULL,
    body_text TEXT,

    -- Recipients (JSON array)
    recipients TEXT NOT NULL,

    -- Workflow
    status ENUM('pending', 'draft', 'ready', 'sent', 'skipped') DEFAULT 'pending',
    reminder_sent_at DATETIME,
    sent_at DATETIME,
    sent_by BIGINT,
    sent_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY unique_template_season (template_id, org_season_id),

    CONSTRAINT fk_campaign_instance_template
        FOREIGN KEY (template_id) REFERENCES sdll_email_campaign_templates(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_campaign_instance_season
        FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- Table 3: Training Types
-- Lookup table for required trainings
-- ============================================================================

CREATE TABLE IF NOT EXISTS sdll_training_types (
    id INT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    required_for VARCHAR(50) DEFAULT 'all',
    expires_after_days INT DEFAULT NULL,
    active TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- Table 4: Training Completions
-- Tracks which users/umpires have completed which trainings
-- ============================================================================

CREATE TABLE IF NOT EXISTS sdll_training_completions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    training_type_id INT NOT NULL,
    user_id BIGINT DEFAULT NULL,
    umpire_profile_id INT DEFAULT NULL,

    completed_at DATE NOT NULL,
    expires_at DATE DEFAULT NULL,
    verification_notes TEXT,
    verified_by BIGINT DEFAULT NULL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Either user_id or umpire_profile_id must be set
    UNIQUE KEY unique_training_user (training_type_id, user_id),
    UNIQUE KEY unique_training_umpire (training_type_id, umpire_profile_id),

    CONSTRAINT fk_training_completion_type
        FOREIGN KEY (training_type_id) REFERENCES sdll_training_types(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_training_completion_user
        FOREIGN KEY (user_id) REFERENCES sdll_users(ID)
        ON DELETE CASCADE,

    CONSTRAINT fk_training_completion_umpire
        FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================================
-- Modify existing tables
-- ============================================================================

-- Add training_date to OrgSeason
ALTER TABLE sdll_org_seasons
    ADD COLUMN training_date DATE DEFAULT NULL;

-- Add lead tracking fields to UmpireProfile
-- Note: These ALTER statements may fail if columns already exist - that's OK
ALTER TABLE sdll_umpire_profiles
    ADD COLUMN lead_source VARCHAR(50) DEFAULT NULL;

ALTER TABLE sdll_umpire_profiles
    ADD COLUMN lead_notes TEXT DEFAULT NULL;

ALTER TABLE sdll_umpire_profiles
    ADD COLUMN target_org_season_id BIGINT DEFAULT NULL;

ALTER TABLE sdll_umpire_profiles
    ADD COLUMN last_contacted_at DATETIME DEFAULT NULL;

-- Add foreign key for target_org_season_id
ALTER TABLE sdll_umpire_profiles
    ADD CONSTRAINT fk_umpire_target_season
    FOREIGN KEY (target_org_season_id) REFERENCES sdll_org_seasons(ID)
    ON DELETE SET NULL;


-- ============================================================================
-- Indexes for performance
-- ============================================================================

CREATE INDEX idx_campaign_templates_active ON sdll_email_campaign_templates(active);
CREATE INDEX idx_campaign_templates_category ON sdll_email_campaign_templates(category);
CREATE INDEX idx_campaign_instances_status ON sdll_email_campaign_instances(status);
CREATE INDEX idx_campaign_instances_trigger_date ON sdll_email_campaign_instances(trigger_date);
CREATE INDEX idx_training_completions_user ON sdll_training_completions(user_id);
CREATE INDEX idx_training_completions_umpire ON sdll_training_completions(umpire_profile_id);
CREATE INDEX idx_umpire_profiles_lead_source ON sdll_umpire_profiles(lead_source);
CREATE INDEX idx_umpire_profiles_target_season ON sdll_umpire_profiles(target_org_season_id);
