-- Migration: Add notification mutes table
-- Allows users to mute specific notifications to suppress repeated alerts

CREATE TABLE sdll_notification_mutes (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- What type of notification is muted
    -- e.g., 'missing_umpire', 'red_flag', 'unassigned_umpire'
    notification_type VARCHAR(50) NOT NULL,

    -- What entity is muted (optional - NULL means mute all of this type)
    entity_type VARCHAR(30),  -- 'game', 'team', 'umpire', etc.
    entity_id BIGINT,         -- ID of the specific entity

    -- When does the mute expire? NULL = indefinitely
    muted_until DATETIME,

    -- Optional reason for muting
    reason VARCHAR(255),

    -- Audit fields
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by_user_id BIGINT,

    -- Indexes
    INDEX idx_mute_type (notification_type),
    INDEX idx_mute_lookup (notification_type, entity_type, entity_id),
    INDEX idx_mute_expiry (muted_until),

    -- Foreign keys
    FOREIGN KEY (created_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL
);
