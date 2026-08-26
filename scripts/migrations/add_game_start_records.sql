-- Migration: Create game_start_records table
-- This table stores first pitch times reported by users (coaches, parents)
-- Used to determine when the "no new inning" time window applies

CREATE TABLE IF NOT EXISTS sdll_game_start_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id INT NOT NULL,
    start_time DATETIME NOT NULL,
    user_id INT DEFAULT NULL,
    session_id VARCHAR(64) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_game_id (game_id),
    INDEX idx_session_id (session_id),

    CONSTRAINT fk_game_start_game FOREIGN KEY (game_id)
        REFERENCES sdll_games(ID) ON DELETE CASCADE,
    CONSTRAINT fk_game_start_user FOREIGN KEY (user_id)
        REFERENCES sdll_users(ID) ON DELETE SET NULL
);
