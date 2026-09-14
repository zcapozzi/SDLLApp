-- Migration: Add Assignr webhook events table
-- Purpose: Track incoming Assignr webhooks for umpire assignment changes
-- Run with: mysql -u user -p database < scripts/add_assignr_webhooks.sql

-- Create the webhook events audit table
CREATE TABLE IF NOT EXISTS sdll_assignr_webhook_events (
    id INT PRIMARY KEY AUTO_INCREMENT,
    event_id BIGINT NOT NULL,              -- Assignr webhook event ID
    topic VARCHAR(100) NOT NULL,           -- "game.official.changed"
    assignr_game_id VARCHAR(20),           -- Extracted from payload
    assignr_assignment_id VARCHAR(20),     -- Extracted from payload
    payload TEXT NOT NULL,                 -- Raw JSON payload

    -- Processing
    status ENUM('received', 'processing', 'completed', 'failed', 'ignored') DEFAULT 'received',
    error_message TEXT,

    -- Local references (populated during processing)
    local_game_id BIGINT,                  -- FK to sdll_games.ID

    -- Notification tracking
    notification_sent TINYINT DEFAULT 0,   -- 1 if alert email was sent
    notification_reason VARCHAR(100),      -- "accepted_within_48h", "declined", etc.

    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed_at DATETIME,

    UNIQUE KEY idx_event_id (event_id),
    INDEX idx_status (status),
    INDEX idx_received_at (received_at),
    INDEX idx_topic (topic),
    INDEX idx_local_game_id (local_game_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verify table was created
SELECT 'sdll_assignr_webhook_events table created successfully' AS status;
