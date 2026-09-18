-- Umpire blockout dates for availability tracking
-- Umpires mark dates they are NOT available to work

CREATE TABLE IF NOT EXISTS sdll_umpire_blockouts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    umpire_profile_id INT NOT NULL,
    blocked_date DATE NOT NULL,
    reason VARCHAR(100),  -- optional note from umpire
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (umpire_profile_id) REFERENCES sdll_umpire_profiles(id) ON DELETE CASCADE,
    UNIQUE KEY uq_profile_date (umpire_profile_id, blocked_date),
    INDEX idx_blocked_date (blocked_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
