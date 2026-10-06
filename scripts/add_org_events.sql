-- Migration: Add org_events table for organization-wide events
-- Events can be scoped to org, sport, league, or team
-- These appear on team/division schedules and sync to Google Calendar

CREATE TABLE sdll_org_events (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Event details
    title VARCHAR(200) NOT NULL,
    description TEXT,
    event_date DATE NOT NULL,
    start_time TIME,
    end_time TIME,
    location VARCHAR(200),
    field_id BIGINT,
    url VARCHAR(500),

    -- Event type: evaluation, signup, meeting, ceremony, practice, other
    event_type VARCHAR(30) DEFAULT 'other',

    -- Scope: org, sport, league, team
    scope VARCHAR(20) DEFAULT 'org',
    sport VARCHAR(20),           -- 'baseball', 'softball', or NULL
    league VARCHAR(50),          -- League name or NULL
    team_id BIGINT,              -- Team ID or NULL

    -- Season context
    year INT NOT NULL,
    is_spring SMALLINT NOT NULL,

    -- Status
    status VARCHAR(20) DEFAULT 'active',
    active SMALLINT DEFAULT 1,

    -- Audit
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by_user_id BIGINT,
    updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,

    -- Foreign keys
    FOREIGN KEY (field_id) REFERENCES sdll_fields(ID) ON DELETE SET NULL,
    FOREIGN KEY (team_id) REFERENCES sdll_team_seasons(team_ID) ON DELETE SET NULL,
    FOREIGN KEY (created_by_user_id) REFERENCES sdll_users(ID) ON DELETE SET NULL,

    -- Indexes
    INDEX idx_org_events_date (event_date),
    INDEX idx_org_events_season (year, is_spring),
    INDEX idx_org_events_scope (scope, sport, league),
    INDEX idx_org_events_status (status, active)
);
