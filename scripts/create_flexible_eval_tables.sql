-- Migration: Create flexible evaluation metrics system
-- Run after create_player_tables.sql

-- Evaluation metrics definition table
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

-- Player evaluation scores - links evaluations to metrics
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

-- Migrate existing data from hard-coded columns to flexible structure
-- First, insert the standard metrics
INSERT INTO sdll_evaluation_metrics (name, display_name, description, category, sort_order) VALUES
('contact', 'Contact', 'Ability to make contact with the ball consistently', 'batting', 10),
('power', 'Power', 'Batting power and ability to drive the ball', 'batting', 20),
('glove', 'Glove', 'Fielding ability and glove work', 'fielding', 30),
('arm', 'Arm', 'Throwing strength and accuracy', 'fielding', 40),
('outfield', 'Outfield', 'Outfield skills including tracking and positioning', 'fielding', 50),
('control', 'Control', 'Pitching control and ability to throw strikes', 'pitching', 60),
('velocity', 'Velocity', 'Pitching speed/velocity', 'pitching', 70),
('speed', 'Speed', 'Running speed (timed)', 'running', 80);

-- Migrate existing scores to the new table
-- This assumes the old columns still exist in sdll_player_evaluations
INSERT INTO sdll_player_evaluation_scores (evaluation_id, metric_id, score)
SELECT e.id, m.id,
    CASE m.name
        WHEN 'contact' THEN e.contact
        WHEN 'power' THEN e.power
        WHEN 'glove' THEN e.glove
        WHEN 'arm' THEN e.arm
        WHEN 'outfield' THEN e.outfield
        WHEN 'control' THEN e.control
        WHEN 'velocity' THEN e.velocity
        WHEN 'speed' THEN e.speed
    END as score
FROM sdll_player_evaluations e
CROSS JOIN sdll_evaluation_metrics m
WHERE CASE m.name
        WHEN 'contact' THEN e.contact
        WHEN 'power' THEN e.power
        WHEN 'glove' THEN e.glove
        WHEN 'arm' THEN e.arm
        WHEN 'outfield' THEN e.outfield
        WHEN 'control' THEN e.control
        WHEN 'velocity' THEN e.velocity
        WHEN 'speed' THEN e.speed
    END IS NOT NULL;

-- After migration is verified, drop old columns from sdll_player_evaluations
-- Run these manually after verifying data migrated correctly:
-- ALTER TABLE sdll_player_evaluations DROP COLUMN contact;
-- ALTER TABLE sdll_player_evaluations DROP COLUMN power;
-- ALTER TABLE sdll_player_evaluations DROP COLUMN glove;
-- ALTER TABLE sdll_player_evaluations DROP COLUMN arm;
-- ALTER TABLE sdll_player_evaluations DROP COLUMN outfield;
-- ALTER TABLE sdll_player_evaluations DROP COLUMN control;
-- ALTER TABLE sdll_player_evaluations DROP COLUMN velocity;
-- ALTER TABLE sdll_player_evaluations DROP COLUMN speed;
