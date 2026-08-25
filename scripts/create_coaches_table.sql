-- Create sdll_coaches table to link users to sports
-- Run this BEFORE running import_coaches.py

CREATE TABLE IF NOT EXISTS sdll_coaches (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    sport ENUM('baseball', 'softball', 'both') NOT NULL,
    season_year INT DEFAULT 2026,
    is_spring TINYINT DEFAULT 1,
    active TINYINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES sdll_users(ID) ON DELETE CASCADE,
    UNIQUE KEY unique_coach_season (user_id, season_year, is_spring)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Index for quick lookups
CREATE INDEX idx_coaches_sport ON sdll_coaches(sport);
CREATE INDEX idx_coaches_season ON sdll_coaches(season_year, is_spring);
CREATE INDEX idx_coaches_active ON sdll_coaches(active);
