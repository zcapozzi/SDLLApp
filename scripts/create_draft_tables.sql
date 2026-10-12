-- Create Draft Tables for SDLL
-- Run this script to create the draft management tables

-- Draft Sessions table
CREATE TABLE IF NOT EXISTS sdll_draft_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_season_id BIGINT NOT NULL,
    league_id BIGINT NOT NULL,
    name VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    draft_order_type VARCHAR(20) DEFAULT 'snake',
    rounds INT DEFAULT 12,
    current_round INT DEFAULT 1,
    current_pick_number INT DEFAULT 1,
    current_team_id BIGINT,
    scheduled_at DATETIME,
    started_at DATETIME,
    completed_at DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by BIGINT,
    FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID),
    FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID),
    FOREIGN KEY (current_team_id) REFERENCES sdll_team_seasons(team_ID),
    FOREIGN KEY (created_by) REFERENCES sdll_users(ID)
);

-- Index for common queries
CREATE INDEX idx_draft_sessions_season ON sdll_draft_sessions(org_season_id);
CREATE INDEX idx_draft_sessions_league ON sdll_draft_sessions(league_id);
CREATE INDEX idx_draft_sessions_status ON sdll_draft_sessions(status);

-- Draft Picks table
CREATE TABLE IF NOT EXISTS sdll_draft_picks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    pick_number INT NOT NULL,
    round_number INT NOT NULL,
    team_id BIGINT NOT NULL,
    player_id INT,
    picked_at DATETIME,
    is_traded SMALLINT DEFAULT 0,
    original_team_id BIGINT,
    notes TEXT,
    FOREIGN KEY (session_id) REFERENCES sdll_draft_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES sdll_team_seasons(team_ID),
    FOREIGN KEY (player_id) REFERENCES sdll_players(id),
    UNIQUE KEY uq_session_pick (session_id, pick_number)
);

-- Indexes for picks
CREATE INDEX idx_draft_picks_session ON sdll_draft_picks(session_id);
CREATE INDEX idx_draft_picks_team ON sdll_draft_picks(team_id);
CREATE INDEX idx_draft_picks_player ON sdll_draft_picks(player_id);

-- Draft Order table (for storing the draft order separately)
CREATE TABLE IF NOT EXISTS sdll_draft_order (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    position INT NOT NULL,
    team_id BIGINT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sdll_draft_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES sdll_team_seasons(team_ID),
    UNIQUE KEY uq_session_position (session_id, position),
    UNIQUE KEY uq_session_team (session_id, team_id)
);

-- Index for draft order
CREATE INDEX idx_draft_order_session ON sdll_draft_order(session_id);

-- Draft Protections table (coach's children, etc.)
CREATE TABLE IF NOT EXISTS sdll_draft_protections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    team_id BIGINT NOT NULL,
    player_id INT NOT NULL,
    round_number INT NOT NULL,
    reason VARCHAR(100) DEFAULT "Coach's child",
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sdll_draft_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES sdll_team_seasons(team_ID),
    FOREIGN KEY (player_id) REFERENCES sdll_players(id),
    UNIQUE KEY uq_session_player_protection (session_id, player_id)
);

-- Indexes for protections
CREATE INDEX idx_draft_protections_session ON sdll_draft_protections(session_id);
CREATE INDEX idx_draft_protections_team ON sdll_draft_protections(team_id);
