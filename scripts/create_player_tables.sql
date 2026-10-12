-- Migration: Create player management tables with flexible evaluation metrics
-- Run against MySQL/Railway production database
--
-- Tables created:
--   sdll_players - Core player records
--   sdll_player_seasons - Per-season participation
--   sdll_evaluation_metrics - Metric definitions (flexible)
--   sdll_player_evaluations - Evaluation header records
--   sdll_player_evaluation_scores - Individual metric scores

-- Players table - core player records
CREATE TABLE IF NOT EXISTS sdll_players (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Player identity (encrypted)
    first_name VARCHAR(500),
    last_name VARCHAR(500),
    name_hash VARCHAR(64),

    -- Parent contact (encrypted)
    parent_email VARCHAR(500),
    parent_email_hash VARCHAR(64),
    secondary_email VARCHAR(500),
    parent_first_name VARCHAR(500),
    parent_last_name VARCHAR(500),
    parent_phone VARCHAR(500),

    -- Link to parent user account
    parent_user_id BIGINT,

    -- Demographics
    birth_date DATE NOT NULL,
    gender VARCHAR(1),

    -- Player code like "bennluk1810"
    player_code VARCHAR(20) UNIQUE,

    -- Program: baseball or softball
    program VARCHAR(20),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_players_name_hash (name_hash),
    INDEX idx_players_email_hash (parent_email_hash),
    INDEX idx_players_code (player_code),
    FOREIGN KEY (parent_user_id) REFERENCES sdll_users(ID)
);

-- Player seasons table - per-season participation
CREATE TABLE IF NOT EXISTS sdll_player_seasons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    player_id INT NOT NULL,
    org_season_id BIGINT NOT NULL,

    -- Registration info
    registration_division VARCHAR(50),

    -- League assignment (FK to sdll_leagues)
    prior_league_id BIGINT,
    placed_league_id BIGINT,

    -- Team assignment (after draft)
    team_id BIGINT,

    -- Coach recommendation
    coach_division_rec VARCHAR(30),

    -- Status: registered, evaluated, placed, drafted
    status VARCHAR(20) DEFAULT 'registered',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_player_org_season (player_id, org_season_id),
    INDEX idx_ps_season (org_season_id),
    INDEX idx_ps_status (status),
    FOREIGN KEY (player_id) REFERENCES sdll_players(id),
    FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID),
    FOREIGN KEY (prior_league_id) REFERENCES sdll_leagues(ID),
    FOREIGN KEY (placed_league_id) REFERENCES sdll_leagues(ID),
    FOREIGN KEY (team_id) REFERENCES sdll_team_seasons(team_ID)
);

-- Player evaluations table - tryout scores
CREATE TABLE IF NOT EXISTS sdll_player_evaluations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    player_id INT NOT NULL,
    org_season_id BIGINT NOT NULL,

    -- Evaluation metadata
    eval_date DATE,
    eval_session VARCHAR(30),  -- "Cactus", "Gila", etc.
    evaluator_id BIGINT,

    -- Skill scores (1.0 - 7.0 scale)
    contact DECIMAL(2,1),
    power DECIMAL(2,1),
    glove DECIMAL(2,1),
    arm DECIMAL(2,1),
    outfield DECIMAL(2,1),
    control DECIMAL(2,1),
    velocity DECIMAL(2,1),
    speed DECIMAL(2,1),

    -- Calculated average
    avg_score DECIMAL(3,2),

    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_pe_player (player_id),
    INDEX idx_pe_season (org_season_id),
    INDEX idx_pe_session (eval_session),
    FOREIGN KEY (player_id) REFERENCES sdll_players(id),
    FOREIGN KEY (org_season_id) REFERENCES sdll_org_seasons(ID),
    FOREIGN KEY (evaluator_id) REFERENCES sdll_users(ID)
);

-- Evaluation metrics definition table (flexible system)
CREATE TABLE IF NOT EXISTS sdll_evaluation_metrics (
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- Metric identity
    name VARCHAR(30) NOT NULL UNIQUE,        -- Internal key: "contact", "power", etc.
    display_name VARCHAR(50) NOT NULL,       -- UI display: "Contact", "Power", etc.
    description TEXT,                        -- How to measure/evaluate this metric

    -- Categorization
    category VARCHAR(30),                    -- "batting", "fielding", "pitching", "running"
    program VARCHAR(20) DEFAULT 'both',      -- "baseball", "softball", "both"

    -- Scoring rules
    min_score DECIMAL(3,1) DEFAULT 1.0,      -- Minimum allowed score
    max_score DECIMAL(3,1) DEFAULT 7.0,      -- Maximum allowed score
    score_increment DECIMAL(2,1) DEFAULT 0.5, -- Score step (0.5 = half points allowed)

    -- Display
    sort_order INT DEFAULT 100,              -- Order in forms/reports
    active TINYINT DEFAULT 1,                -- Whether currently in use

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_metrics_category (category),
    INDEX idx_metrics_program (program),
    INDEX idx_metrics_active (active)
);

-- Player evaluation scores - links evaluations to metrics (flexible system)
CREATE TABLE IF NOT EXISTS sdll_player_evaluation_scores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    evaluation_id INT NOT NULL,
    metric_id INT NOT NULL,
    score DECIMAL(3,1),                      -- The actual score value

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_eval_metric (evaluation_id, metric_id),
    INDEX idx_pes_evaluation (evaluation_id),
    INDEX idx_pes_metric (metric_id),
    FOREIGN KEY (evaluation_id) REFERENCES sdll_player_evaluations(id) ON DELETE CASCADE,
    FOREIGN KEY (metric_id) REFERENCES sdll_evaluation_metrics(id)
);

-- Insert standard evaluation metrics
INSERT IGNORE INTO sdll_evaluation_metrics (name, display_name, description, category, sort_order) VALUES
('contact', 'Contact', 'Ability to make contact with the ball consistently', 'batting', 10),
('power', 'Power', 'Batting power and ability to drive the ball', 'batting', 20),
('glove', 'Glove', 'Fielding ability and glove work', 'fielding', 30),
('arm', 'Arm', 'Throwing strength and accuracy', 'fielding', 40),
('outfield', 'Outfield', 'Outfield skills including tracking and positioning', 'fielding', 50),
('control', 'Control', 'Pitching control and ability to throw strikes', 'pitching', 60),
('velocity', 'Velocity', 'Pitching speed/velocity', 'pitching', 70),
('speed', 'Speed', 'Running speed (timed)', 'running', 80);
