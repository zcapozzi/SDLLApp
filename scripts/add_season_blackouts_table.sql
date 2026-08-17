-- Add season blackouts table for league-wide blackout dates
-- These are dates when no games/practices should be scheduled (e.g., Labor Day Weekend)

CREATE TABLE IF NOT EXISTS sdll_season_blackouts (
    ID BIGINT AUTO_INCREMENT PRIMARY KEY,
    year INT NOT NULL,
    is_spring SMALLINT NOT NULL,
    blackout_date DATE NOT NULL,
    reason VARCHAR(200),
    active SMALLINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY unique_blackout (year, is_spring, blackout_date),
    INDEX idx_season (year, is_spring, active),
    INDEX idx_date (blackout_date)
);
