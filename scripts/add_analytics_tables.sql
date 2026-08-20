-- Analytics tables for privacy-respecting first-party tracking
-- See privacyApproach.md for privacy principles

-- Page views table (anonymous tracking)
CREATE TABLE IF NOT EXISTS sdll_page_views (
    ID BIGINT AUTO_INCREMENT PRIMARY KEY,
    page_type VARCHAR(50) NOT NULL COMMENT 'team_schedule, calendar, privacy, etc.',
    page_context VARCHAR(100) COMMENT 'Team token, year/season, etc.',
    session_id VARCHAR(64) COMMENT 'Anonymous cookie-based session',
    ip_hash VARCHAR(64) COMMENT 'SHA256 of IP (privacy-safe)',
    user_agent VARCHAR(500),
    device_type VARCHAR(20) COMMENT 'mobile, tablet, desktop',
    viewport_width INT COMMENT 'Updated by JS beacon',
    viewport_height INT COMMENT 'Updated by JS beacon',
    referrer VARCHAR(500),
    time_on_page_seconds INT COMMENT 'Updated by JS beacon on unload',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session (session_id),
    INDEX idx_created (created_at),
    INDEX idx_page_type (page_type, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Self-hosted ads table
CREATE TABLE IF NOT EXISTS sdll_ads (
    ID BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL COMMENT 'Internal name',
    sponsor VARCHAR(100) COMMENT 'Displayed as Presented by X',
    headline VARCHAR(100) COMMENT 'Optional headline text',
    description VARCHAR(300) COMMENT 'Optional description text',
    image_url VARCHAR(500) COMMENT 'Path to self-hosted image',
    click_url VARCHAR(500) COMMENT 'Redirect URL on click',
    alt_text VARCHAR(200) COMMENT 'Accessibility text',
    target_leagues VARCHAR(200) COMMENT 'Comma-separated leagues or NULL for all',
    start_date DATE,
    end_date DATE,
    priority INT DEFAULT 1 COMMENT 'Higher = more likely to show',
    active SMALLINT DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_active_dates (active, start_date, end_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Ad impressions table
CREATE TABLE IF NOT EXISTS sdll_ad_impressions (
    ID BIGINT AUTO_INCREMENT PRIMARY KEY,
    ad_id BIGINT NOT NULL,
    impression_token VARCHAR(64) UNIQUE COMMENT 'For linking to clicks',
    page_view_id BIGINT,
    session_id VARCHAR(64),
    page_context VARCHAR(100) COMMENT 'Team token, etc.',
    device_type VARCHAR(20),
    viewport_width INT,
    was_viewable SMALLINT DEFAULT 0 COMMENT '1 if met IAB standard (50% visible 1+ sec)',
    viewable_seconds FLOAT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ad_id) REFERENCES sdll_ads(ID),
    FOREIGN KEY (page_view_id) REFERENCES sdll_page_views(ID),
    INDEX idx_ad (ad_id),
    INDEX idx_impression_token (impression_token),
    INDEX idx_session (session_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Ad clicks table
CREATE TABLE IF NOT EXISTS sdll_ad_clicks (
    ID BIGINT AUTO_INCREMENT PRIMARY KEY,
    ad_id BIGINT NOT NULL,
    impression_id BIGINT,
    click_token VARCHAR(64) UNIQUE COMMENT 'For validation',
    session_id VARCHAR(64),
    time_to_click_ms INT COMMENT 'Time from page load to click',
    click_x INT COMMENT 'Click position for fraud detection',
    click_y INT,
    validated SMALLINT DEFAULT 0 COMMENT '1 if passed validation',
    validation_notes VARCHAR(200) COMMENT 'Reason if failed',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ad_id) REFERENCES sdll_ads(ID),
    FOREIGN KEY (impression_id) REFERENCES sdll_ad_impressions(ID),
    INDEX idx_ad (ad_id),
    INDEX idx_click_token (click_token),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert a simple "Presented by SDLL" placeholder ad
INSERT INTO sdll_ads (name, sponsor, headline, description, click_url, alt_text, priority, active)
VALUES (
    'SDLL Placeholder',
    'South Durham Little League',
    'Go SDLL!',
    'Proud to serve Durham''s youth baseball and softball community since 1968.',
    'https://southdurhamlittleleague.org',
    'South Durham Little League',
    1,
    1
);
