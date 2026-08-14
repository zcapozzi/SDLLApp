-- Create table for persistent schedule proposals
-- This replaces session-based storage for schedule proposals

CREATE TABLE IF NOT EXISTS sdll_schedule_proposals (
    ID BIGINT PRIMARY KEY AUTO_INCREMENT,
    year INT NOT NULL,
    is_spring SMALLINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- 'draft', 'review', 'accepted'
    created_by BIGINT,  -- FK to sdll_users
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    data JSON NOT NULL,  -- The full proposal data (games, violations, warnings, summary)

    -- Only one active proposal per season
    UNIQUE KEY unique_season_proposal (year, is_spring, status),

    FOREIGN KEY (created_by) REFERENCES sdll_users(ID) ON DELETE SET NULL
);

-- Index for quick lookups
CREATE INDEX idx_proposals_season ON sdll_schedule_proposals(year, is_spring);
