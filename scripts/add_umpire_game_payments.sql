-- Migration: Add umpire game payments table
-- Date: 2026-09-09
-- Purpose: Track game-specific payment multipliers for umpires (e.g., 2x incentive games)
-- Note: Using standard MySQL syntax (no MariaDB-specific IF EXISTS)

CREATE TABLE sdll_umpire_game_payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id BIGINT NULL,
    umpire_profile_id INT NULL,
    assignr_official_id INT NULL,
    multiplier DECIMAL(3,2) DEFAULT 1.00,
    notes VARCHAR(255) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by BIGINT NULL,

    -- Foreign keys
    FOREIGN KEY (game_id) REFERENCES sdll_games(ID) ON DELETE SET NULL,
    FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES sdll_users(ID) ON DELETE SET NULL,

    -- Indexes for lookups
    INDEX idx_game_id (game_id),
    INDEX idx_umpire_profile_id (umpire_profile_id),
    INDEX idx_assignr_official_id (assignr_official_id),
    INDEX idx_game_official (game_id, assignr_official_id)
);

-- Add comment for documentation
ALTER TABLE sdll_umpire_game_payments COMMENT = 'Tracks payment multipliers for special games (incentive games, etc.)';
