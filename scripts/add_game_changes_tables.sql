-- Migration: Add tables for game change tracking, notification queue, and umpire assignments
-- Run this migration to enable the new game editing system

-- 1. Game Change Tracking Table
-- Logs all modifications to games with who/what/when/why
CREATE TABLE IF NOT EXISTS sdll_game_changes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id BIGINT NOT NULL,
    changed_by BIGINT NOT NULL,  -- user_id
    changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    change_type ENUM('create', 'update', 'cancel', 'reschedule', 'delete') NOT NULL,

    -- What changed (store old and new values as JSON)
    field_changed VARCHAR(50),  -- 'date', 'time', 'field', 'status', etc.
    old_value TEXT,
    new_value TEXT,

    -- All changes in one update as JSON (for batch changes)
    changes_json JSON,

    -- Optional reason/notes from user
    reason TEXT,

    -- Denormalized for easier querying
    game_date DATE,
    league VARCHAR(50),
    home_team_id INT,
    away_team_id INT,

    FOREIGN KEY (game_id) REFERENCES sdll_games(ID) ON DELETE CASCADE,
    FOREIGN KEY (changed_by) REFERENCES sdll_users(ID),
    INDEX idx_game_changes_game_id (game_id),
    INDEX idx_game_changes_changed_at (changed_at),
    INDEX idx_game_changes_league (league),
    INDEX idx_game_changes_game_date (game_date),
    INDEX idx_game_changes_changed_by (changed_by)
);

-- 2. Notification Queue Table
-- Stores pending notifications that can be reviewed before sending
CREATE TABLE IF NOT EXISTS sdll_notification_queue (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- What triggered this notification
    change_id INT,  -- FK to sdll_game_changes
    game_id BIGINT NOT NULL,

    -- Recipient info
    recipient_type ENUM('admin', 'coach', 'umpire', 'parent') NOT NULL,
    recipient_id INT,  -- user_id if applicable
    recipient_email VARCHAR(255) NOT NULL,
    recipient_name VARCHAR(100),

    -- Notification content
    subject VARCHAR(255) NOT NULL,
    body_text TEXT NOT NULL,
    body_html TEXT,

    -- Status tracking
    status ENUM('pending', 'sent', 'failed', 'skipped') NOT NULL DEFAULT 'pending',
    sent_at DATETIME,
    error_message TEXT,

    -- Grouping for batch sends
    batch_id VARCHAR(50),

    FOREIGN KEY (change_id) REFERENCES sdll_game_changes(id) ON DELETE SET NULL,
    FOREIGN KEY (game_id) REFERENCES sdll_games(ID) ON DELETE CASCADE,
    INDEX idx_notification_queue_status (status),
    INDEX idx_notification_queue_recipient_type (recipient_type),
    INDEX idx_notification_queue_batch_id (batch_id),
    INDEX idx_notification_queue_created_at (created_at),
    INDEX idx_notification_queue_game_id (game_id)
);

-- 3. Umpire Assignments Table
-- Tracks which umpires are assigned to which games
CREATE TABLE IF NOT EXISTS sdll_umpire_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id BIGINT NOT NULL,
    umpire_id BIGINT NOT NULL,  -- user_id of umpire
    role ENUM('plate', 'base', 'field') NOT NULL DEFAULT 'plate',
    assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by BIGINT,  -- user_id who made assignment

    FOREIGN KEY (game_id) REFERENCES sdll_games(ID) ON DELETE CASCADE,
    FOREIGN KEY (umpire_id) REFERENCES sdll_users(ID),
    FOREIGN KEY (assigned_by) REFERENCES sdll_users(ID),
    UNIQUE KEY unique_umpire_assignment (game_id, umpire_id, role),
    INDEX idx_umpire_assignments_umpire (umpire_id),
    INDEX idx_umpire_assignments_game (game_id)
);

-- 4. Add index to existing sdll_games table for faster lookups if not exists
-- (Run only if index doesn't exist)
-- CREATE INDEX IF NOT EXISTS idx_games_date ON sdll_games(game_date);
-- CREATE INDEX IF NOT EXISTS idx_games_league ON sdll_games(league);
-- CREATE INDEX IF NOT EXISTS idx_games_status ON sdll_games(status);
