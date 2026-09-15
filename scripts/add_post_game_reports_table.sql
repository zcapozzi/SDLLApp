-- Migration: Add post-game reports table
-- Purpose: Enable coaches to submit post-game data (scores, umpire evaluations)
-- Date: 2026-09-15

-- Create post-game reports table
CREATE TABLE IF NOT EXISTS sdll_post_game_reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id BIGINT NOT NULL,
    team_id BIGINT NOT NULL,

    -- Status: pending, submitted, not_played
    status VARCHAR(20) DEFAULT 'pending',

    -- Score (from this team's perspective)
    our_score SMALLINT DEFAULT NULL,
    opponent_score SMALLINT DEFAULT NULL,

    -- Innings
    innings_batted SMALLINT DEFAULT NULL,
    innings_fielded SMALLINT DEFAULT NULL,

    -- Umpire evaluation
    umpire_name VARCHAR(100) DEFAULT NULL,
    umpire_rating VARCHAR(20) DEFAULT NULL,
    umpire_comments TEXT DEFAULT NULL,

    -- Not played tracking
    not_played_reason VARCHAR(50) DEFAULT NULL,
    not_played_notes TEXT DEFAULT NULL,

    -- Submission tracking
    submitted_by_user_id BIGINT DEFAULT NULL,
    submitted_by_role VARCHAR(20) DEFAULT NULL,
    submitted_at DATETIME DEFAULT NULL,

    -- Email tracking
    email_sent_at DATETIME DEFAULT NULL,
    email_opened_at DATETIME DEFAULT NULL,

    -- Flagged for review
    is_flagged BOOLEAN DEFAULT FALSE,
    flag_reason VARCHAR(200) DEFAULT NULL,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (game_id) REFERENCES sdll_games(ID) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES sdll_team_seasons(team_ID) ON DELETE CASCADE,
    FOREIGN KEY (submitted_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL,

    -- Unique constraint: one report per team per game
    UNIQUE KEY uq_postgame_game_team (game_id, team_id),

    -- Indexes for common queries
    INDEX idx_postgame_game_id (game_id),
    INDEX idx_postgame_team_id (team_id),
    INDEX idx_postgame_status (status),
    INDEX idx_postgame_umpire_name (umpire_name),
    INDEX idx_postgame_created_at (created_at)
);

-- Add postgame_enabled field to league_seasons table
ALTER TABLE sdll_league_seasons
ADD COLUMN postgame_enabled BOOLEAN DEFAULT FALSE;

-- Add index for efficient querying
ALTER TABLE sdll_league_seasons
ADD INDEX idx_league_seasons_postgame (postgame_enabled);
