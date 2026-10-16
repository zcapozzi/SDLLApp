-- Migration: Create sdll_callup_requests table for call-up tracking
-- Run this against the production database to enable the call-up tracking feature

CREATE TABLE IF NOT EXISTS sdll_callup_requests (
    id INT PRIMARY KEY AUTO_INCREMENT,

    -- Context - which player for which game
    player_season_id BIGINT NOT NULL,
    game_id BIGINT NOT NULL,
    target_team_id BIGINT NOT NULL,

    -- Request details
    requested_by BIGINT NOT NULL,
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    contact_email VARCHAR(255),

    -- Status: pending, accepted, declined, no_response, cancelled
    status VARCHAR(20) DEFAULT 'pending',

    -- Response tracking
    responded_at DATETIME NULL,
    notes TEXT,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NULL ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign key constraints
    CONSTRAINT fk_callup_player_season FOREIGN KEY (player_season_id)
        REFERENCES sdll_player_seasons(id) ON DELETE CASCADE,
    CONSTRAINT fk_callup_game FOREIGN KEY (game_id)
        REFERENCES sdll_games(ID) ON DELETE CASCADE,
    CONSTRAINT fk_callup_target_team FOREIGN KEY (target_team_id)
        REFERENCES sdll_team_seasons(team_ID) ON DELETE CASCADE,
    CONSTRAINT fk_callup_requested_by FOREIGN KEY (requested_by)
        REFERENCES sdll_users(ID) ON DELETE CASCADE,

    -- Indexes for common queries
    INDEX idx_callup_player (player_season_id),
    INDEX idx_callup_game (game_id),
    INDEX idx_callup_status (status),
    INDEX idx_callup_requested_at (requested_at)
);
