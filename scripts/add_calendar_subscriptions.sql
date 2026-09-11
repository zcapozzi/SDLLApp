-- Migration: Add calendar subscriptions tracking table
-- Tracks unique calendar sync subscriptions per team

CREATE TABLE IF NOT EXISTS sdll_calendar_subscriptions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    team_token VARCHAR(50) NOT NULL,
    user_agent_hash VARCHAR(64) NOT NULL,
    sync_type VARCHAR(20),
    device_type VARCHAR(20),
    first_access_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_access_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    access_count INT DEFAULT 1,

    INDEX idx_team_token (team_token),
    INDEX idx_first_access (first_access_at),
    UNIQUE INDEX uix_calendar_sub_token_ua (team_token, user_agent_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
