-- Migration: Add sdll_app_errors table for Tier I/II error reporting
-- Run this on the Railway database

CREATE TABLE IF NOT EXISTS sdll_app_errors (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Error classification
    tier SMALLINT NOT NULL DEFAULT 2 COMMENT '1=critical/immediate, 2=digest',
    context VARCHAR(100) NOT NULL COMMENT 'e.g., page_view_tracking, ad_click',
    error_type VARCHAR(100) NOT NULL COMMENT 'Exception class name',
    error_message TEXT NOT NULL,
    traceback TEXT,

    -- Request context
    request_method VARCHAR(10),
    request_path VARCHAR(500),
    request_user_agent VARCHAR(500),
    user_id INT COMMENT 'Logged-in user ID if available',

    -- Status tracking
    notified BOOLEAN DEFAULT FALSE COMMENT 'Has this been reported?',
    notified_at DATETIME,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at DATETIME,
    resolved_by INT COMMENT 'User ID of admin who resolved',

    -- For grouping similar errors
    error_hash VARCHAR(64) COMMENT 'Hash of context+type+message for grouping',

    -- Indexes
    INDEX idx_tier (tier),
    INDEX idx_created_at (created_at),
    INDEX idx_notified (notified),
    INDEX idx_resolved (resolved),
    INDEX idx_error_hash (error_hash),
    INDEX idx_context (context)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verify the table was created
SELECT 'sdll_app_errors table created successfully' AS status;
DESCRIBE sdll_app_errors;
