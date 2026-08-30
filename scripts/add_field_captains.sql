-- Migration: Add field captains table
-- Links users with fieldCaptain role to specific fields they manage

CREATE TABLE IF NOT EXISTS sdll_field_captains (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    field_id BIGINT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by BIGINT NULL,
    FOREIGN KEY (user_id) REFERENCES sdll_users(ID) ON DELETE CASCADE,
    FOREIGN KEY (field_id) REFERENCES sdll_fields(ID) ON DELETE CASCADE,
    UNIQUE KEY unique_user_field (user_id, field_id),
    INDEX idx_field (field_id),
    INDEX idx_user (user_id)
);
