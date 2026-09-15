-- Migration: Create sdll_access_requests table for self-service access requests
-- Run this on production database before deploying the feature

CREATE TABLE sdll_access_requests (
    id INT PRIMARY KEY AUTO_INCREMENT,
    request_type VARCHAR(20) NOT NULL COMMENT 'parent, coach, or admin',
    status VARCHAR(20) DEFAULT 'pending' COMMENT 'email_pending, pending, approved, rejected, expired',

    -- Encrypted PII fields (same pattern as sdll_users)
    first_name VARCHAR(500) NOT NULL COMMENT 'Encrypted',
    last_name VARCHAR(500) NOT NULL COMMENT 'Encrypted',
    email VARCHAR(500) NOT NULL COMMENT 'Encrypted',
    email_hash VARCHAR(64) NOT NULL COMMENT 'For email lookup',
    phone VARCHAR(500) DEFAULT NULL COMMENT 'Encrypted',

    -- Email verification (for parent requests)
    verification_token VARCHAR(64) UNIQUE DEFAULT NULL,
    verification_expires DATETIME DEFAULT NULL,
    email_verified_at DATETIME DEFAULT NULL,

    -- Coach-specific: link to team
    team_id BIGINT DEFAULT NULL,

    -- Admin-specific: free-text roles description
    requested_roles TEXT DEFAULT NULL,

    -- Processing metadata
    processed_at DATETIME DEFAULT NULL,
    processed_by BIGINT DEFAULT NULL,
    rejection_reason TEXT DEFAULT NULL,
    created_user_id BIGINT DEFAULT NULL,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    -- Organization (for multi-org support)
    org_id BIGINT DEFAULT 1,

    -- Indexes
    INDEX idx_email_hash (email_hash),
    INDEX idx_status (status),
    INDEX idx_request_type_status (request_type, status),
    INDEX idx_org_status (org_id, status),
    INDEX idx_created_at (created_at),

    -- Foreign keys
    CONSTRAINT fk_access_request_team FOREIGN KEY (team_id)
        REFERENCES sdll_team_seasons(team_ID) ON DELETE SET NULL,
    CONSTRAINT fk_access_request_processor FOREIGN KEY (processed_by)
        REFERENCES sdll_users(ID) ON DELETE SET NULL,
    CONSTRAINT fk_access_request_created_user FOREIGN KEY (created_user_id)
        REFERENCES sdll_users(ID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Note: Email uniqueness is NOT enforced at database level since:
-- 1. Someone could have a rejected request and then submit a new one
-- 2. A user might exist and then submit a parent request (should be caught in app logic)
-- Application logic handles duplicate checking appropriately.
