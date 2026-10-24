-- QR Campaign tables for onboarding flows
-- Run with: mysql -u user -p database < scripts/add_qr_campaigns.sql

-- Main campaigns table
CREATE TABLE IF NOT EXISTS sdll_qr_campaigns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    campaign_type VARCHAR(30) NOT NULL,
    token VARCHAR(32) NOT NULL UNIQUE,
    org_season_id BIGINT,
    sport VARCHAR(20),
    active SMALLINT DEFAULT 1,
    expires_at DATETIME,
    welcome_message TEXT,
    completion_redirect_url VARCHAR(500),
    scan_count INT DEFAULT 0,
    registration_count INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by BIGINT,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,
    org_id BIGINT DEFAULT 1,
    INDEX idx_token (token),
    INDEX idx_campaign_type (campaign_type),
    INDEX idx_active (active),
    FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES sdll_users(ID) ON DELETE SET NULL
);

-- Scan tracking table
CREATE TABLE IF NOT EXISTS sdll_qr_campaign_scans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    campaign_id INT NOT NULL,
    user_id BIGINT,
    outcome VARCHAR(30),
    user_agent VARCHAR(500),
    ip_hash VARCHAR(64),
    scanned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_campaign_id (campaign_id),
    INDEX idx_scanned_at (scanned_at),
    FOREIGN KEY (campaign_id) REFERENCES sdll_qr_campaigns(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL
);
