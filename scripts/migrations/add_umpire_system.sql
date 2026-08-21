-- =============================================================================
-- Migration: Add Umpire Scheduling System
-- Version: 1.0
-- Date: 2026-08-21
-- Description: Creates tables for umpire profiles, partners, game assignments,
--              delegation rules, and payments.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Umpire Partners (Dynamic, Diamond, etc.)
-- Must be created first as it's referenced by other tables
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sdll_umpire_partners (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    short_code VARCHAR(20),
    contact_name VARCHAR(200),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    notification_preference VARCHAR(20) DEFAULT 'weekly',
    active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES sdll_organizations(ID),
    INDEX idx_org (org_id),
    INDEX idx_active (active),
    UNIQUE KEY uk_org_code (org_id, short_code)
);

-- Seed default partners for SDLL (org_id = 1)
INSERT INTO sdll_umpire_partners (org_id, name, short_code, notification_preference)
VALUES
    (1, 'Diamond Umpires', 'DIA', 'weekly'),
    (1, 'Dynamic Umpires', 'DYN', 'weekly')
ON DUPLICATE KEY UPDATE name = VALUES(name);


-- -----------------------------------------------------------------------------
-- 2. Umpire Profiles (linked to sdll_users for login)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sdll_umpire_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    birth_date DATE,
    parent_name VARCHAR(500),       -- Encrypted
    parent_email VARCHAR(500),      -- Encrypted
    parent_email_hash VARCHAR(64),  -- For lookup
    parent_phone VARCHAR(500),      -- Encrypted
    status VARCHAR(20) DEFAULT 'active',
    is_kid_pitch_eligible BOOLEAN DEFAULT FALSE,
    pay_scale VARCHAR(50),
    assignr_id VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES sdll_users(ID) ON DELETE CASCADE,
    INDEX idx_status (status),
    INDEX idx_assignr (assignr_id)
);


-- -----------------------------------------------------------------------------
-- 3. Game Umpire Assignments
-- Links games to either SDLL umpires (via profile) or partner companies
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sdll_game_umpires (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id BIGINT NOT NULL,
    umpire_profile_id INT,           -- SDLL umpire (via profile)
    partner_id INT,                   -- OR umpire partner company
    role VARCHAR(20) DEFAULT 'umpire',
    position_number SMALLINT DEFAULT 1,
    status VARCHAR(20) DEFAULT 'assigned',
    confirmed_at DATETIME,
    confirmation_method VARCHAR(20),
    base_pay DECIMAL(6,2),
    bonus_multiplier DECIMAL(3,2) DEFAULT 1.0,
    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    assigned_by BIGINT,
    notes TEXT,
    was_previously_cancelled BOOLEAN DEFAULT FALSE,
    cancelled_at DATETIME,
    cancelled_by BIGINT,
    FOREIGN KEY (game_id) REFERENCES sdll_games(ID) ON DELETE CASCADE,
    FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id) ON DELETE SET NULL,
    FOREIGN KEY (partner_id) REFERENCES sdll_umpire_partners(id) ON DELETE SET NULL,
    FOREIGN KEY (assigned_by) REFERENCES sdll_users(ID) ON DELETE SET NULL,
    FOREIGN KEY (cancelled_by) REFERENCES sdll_users(ID) ON DELETE SET NULL,
    INDEX idx_game (game_id),
    INDEX idx_umpire (umpire_profile_id),
    INDEX idx_partner (partner_id),
    INDEX idx_status (status)
);


-- -----------------------------------------------------------------------------
-- 4. Umpire Delegation Rules (percentage splits by league)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sdll_umpire_delegation_rules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id BIGINT NOT NULL,
    league_id BIGINT NOT NULL,
    year SMALLINT,                    -- NULL = default for all seasons
    is_spring BOOLEAN,                -- NULL = default for all seasons
    academy_pct SMALLINT DEFAULT 0,   -- SDLL umpires %
    diamond_pct SMALLINT DEFAULT 0,
    dynamic_pct SMALLINT DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (org_id) REFERENCES sdll_organizations(ID),
    FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID),
    INDEX idx_league (league_id),
    INDEX idx_season (year, is_spring),
    UNIQUE KEY uk_league_season (league_id, year, is_spring)
);


-- -----------------------------------------------------------------------------
-- 5. Umpire Delegation Overrides (keyword-based routing)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sdll_umpire_delegation_overrides (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_id BIGINT NOT NULL,
    keyword VARCHAR(50) NOT NULL,
    target_type VARCHAR(20) NOT NULL,
    partner_id INT,
    description VARCHAR(200),
    active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (org_id) REFERENCES sdll_organizations(ID),
    FOREIGN KEY (partner_id) REFERENCES sdll_umpire_partners(id) ON DELETE SET NULL,
    INDEX idx_org (org_id),
    UNIQUE KEY uk_org_keyword (org_id, keyword)
);

-- Seed default overrides for SDLL
INSERT INTO sdll_umpire_delegation_overrides (org_id, keyword, target_type, partner_id, description)
VALUES
    (1, 'Young Umpire', 'academy', NULL, 'Force assignment to SDLL youth umpire'),
    (1, 'Vance', 'partner', (SELECT id FROM sdll_umpire_partners WHERE org_id = 1 AND short_code = 'DIA' LIMIT 1), 'Force assignment to Diamond (Vance)')
ON DUPLICATE KEY UPDATE description = VALUES(description);


-- -----------------------------------------------------------------------------
-- 6. Coach Seasons (coach contact info per team per season)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sdll_coach_seasons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    team_id BIGINT NOT NULL,
    name VARCHAR(500) NOT NULL,        -- Encrypted
    email VARCHAR(500),                 -- Encrypted
    email_hash VARCHAR(64),             -- For lookup
    phone VARCHAR(500),                 -- Encrypted
    role VARCHAR(20) DEFAULT 'head',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (team_id) REFERENCES sdll_team_seasons(team_ID) ON DELETE CASCADE,
    INDEX idx_team (team_id)
);


-- -----------------------------------------------------------------------------
-- 7. Umpire Payments
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sdll_umpire_payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    umpire_profile_id INT NOT NULL,
    pay_period_start DATE NOT NULL,
    pay_period_end DATE NOT NULL,
    games_count SMALLINT DEFAULT 0,
    base_amount DECIMAL(8,2) DEFAULT 0,
    bonus_amount DECIMAL(8,2) DEFAULT 0,
    total_amount DECIMAL(8,2) DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    paid_at DATETIME,
    paid_by BIGINT,
    payment_method VARCHAR(50),
    payment_reference VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (paid_by) REFERENCES sdll_users(ID) ON DELETE SET NULL,
    INDEX idx_umpire (umpire_profile_id),
    INDEX idx_status (status),
    INDEX idx_period (pay_period_start, pay_period_end)
);


-- -----------------------------------------------------------------------------
-- 8. Modify sdll_leagues - Add umpire configuration columns
-- These ALTER TABLE statements may fail if columns already exist - that's OK
-- -----------------------------------------------------------------------------
-- Run these separately and ignore errors if columns exist
-- ALTER TABLE sdll_leagues ADD COLUMN umpire_count SMALLINT DEFAULT 1;
-- ALTER TABLE sdll_leagues ADD COLUMN umpire_source VARCHAR(20) DEFAULT 'sdll';
-- ALTER TABLE sdll_leagues ADD COLUMN default_partner_id INT;
-- ALTER TABLE sdll_leagues ADD COLUMN requires_kid_pitch BOOLEAN DEFAULT FALSE;
-- ALTER TABLE sdll_leagues ADD COLUMN uses_large_field BOOLEAN DEFAULT FALSE;


-- -----------------------------------------------------------------------------
-- 9. Seed default delegation rules for SDLL leagues
-- Run this AFTER the above tables are created
-- -----------------------------------------------------------------------------
INSERT INTO sdll_umpire_delegation_rules (org_id, league_id, academy_pct, diamond_pct, dynamic_pct)
SELECT
    1 as org_id,
    l.ID as league_id,
    CASE l.display_name
        WHEN 'Rookie' THEN 100
        WHEN 'A' THEN 100
        WHEN 'AA' THEN 50
        WHEN 'AAA' THEN 33
        WHEN 'Majors' THEN 0
        WHEN 'Intermediate' THEN 0
        WHEN 'Juniors' THEN 0
        WHEN 'SB Rookie' THEN 100
        WHEN 'SB Majors' THEN 0
        WHEN 'Cactus' THEN 0
        WHEN 'Grapefruit' THEN 0
        ELSE 50
    END as academy_pct,
    CASE l.display_name
        WHEN 'Rookie' THEN 0
        WHEN 'A' THEN 0
        WHEN 'AA' THEN 25
        WHEN 'AAA' THEN 33
        WHEN 'Majors' THEN 50
        WHEN 'Intermediate' THEN 50
        WHEN 'Juniors' THEN 50
        WHEN 'SB Rookie' THEN 0
        WHEN 'SB Majors' THEN 100
        WHEN 'Cactus' THEN 50
        WHEN 'Grapefruit' THEN 50
        ELSE 25
    END as diamond_pct,
    CASE l.display_name
        WHEN 'Rookie' THEN 0
        WHEN 'A' THEN 0
        WHEN 'AA' THEN 25
        WHEN 'AAA' THEN 34
        WHEN 'Majors' THEN 50
        WHEN 'Intermediate' THEN 50
        WHEN 'Juniors' THEN 50
        WHEN 'SB Rookie' THEN 0
        WHEN 'SB Majors' THEN 0
        WHEN 'Cactus' THEN 50
        WHEN 'Grapefruit' THEN 50
        ELSE 25
    END as dynamic_pct
FROM sdll_leagues l
WHERE l.active = 1
ON DUPLICATE KEY UPDATE
    academy_pct = VALUES(academy_pct),
    diamond_pct = VALUES(diamond_pct),
    dynamic_pct = VALUES(dynamic_pct);


-- -----------------------------------------------------------------------------
-- 10. Update league umpire config based on pitch type
-- -----------------------------------------------------------------------------
UPDATE sdll_leagues
SET
    umpire_count = CASE
        WHEN pitch_type = 'tee_ball' THEN 0
        WHEN display_name IN ('Majors', 'Intermediate', 'Juniors', 'SB Majors') THEN 2
        ELSE 1
    END,
    requires_kid_pitch = CASE
        WHEN pitch_type = 'kid_pitch' THEN TRUE
        ELSE FALSE
    END,
    uses_large_field = CASE
        WHEN display_name IN ('AAA', 'Majors', 'Intermediate', 'Juniors', 'SB Majors') THEN TRUE
        ELSE FALSE
    END
WHERE active = 1;


-- =============================================================================
-- VERIFICATION QUERIES (run these to verify migration success)
-- =============================================================================

-- Check all tables created:
-- SHOW TABLES LIKE 'sdll_umpire%';
-- SHOW TABLES LIKE 'sdll_coach%';

-- Check delegation rules seeded:
-- SELECT l.display_name, r.academy_pct, r.diamond_pct, r.dynamic_pct
-- FROM sdll_umpire_delegation_rules r
-- JOIN sdll_leagues l ON l.ID = r.league_id
-- ORDER BY l.sort_order;

-- Check partners created:
-- SELECT * FROM sdll_umpire_partners;

-- Check league umpire config:
-- SELECT display_name, umpire_count, umpire_source, requires_kid_pitch, uses_large_field
-- FROM sdll_leagues WHERE active = 1 ORDER BY sort_order;
