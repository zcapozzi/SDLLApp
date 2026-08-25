-- Create sdll_coaches table to link users to sports
-- Season assignments are handled via sdll_coach_seasons -> sdll_team_seasons

CREATE TABLE IF NOT EXISTS sdll_coaches (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    sport ENUM('baseball', 'softball', 'both') NOT NULL,
    status VARCHAR(15) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES sdll_users(ID) ON DELETE CASCADE,
    UNIQUE KEY unique_coach_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Index for quick lookups
CREATE INDEX idx_coaches_sport ON sdll_coaches(sport);
CREATE INDEX idx_coaches_status ON sdll_coaches(status);
