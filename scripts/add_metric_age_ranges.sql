-- Migration: Add age-specific score ranges for evaluation metrics
--
-- This adds support for different score ranges (min/max/increment) for different
-- age groups. For example, younger players (ages 4-6) might use a simpler 1-3 scale
-- while older players (ages 10-12) use the full 1-7 scale.
--
-- Usage: mysql -u username -p database_name < scripts/add_metric_age_ranges.sql

CREATE TABLE IF NOT EXISTS sdll_evaluation_metric_age_ranges (
    id INT AUTO_INCREMENT PRIMARY KEY,
    metric_id INT NOT NULL,
    min_age SMALLINT NOT NULL,
    max_age SMALLINT NOT NULL,
    min_score DECIMAL(3,1) NOT NULL,
    max_score DECIMAL(3,1) NOT NULL,
    score_increment DECIMAL(2,1) NOT NULL DEFAULT 0.5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key to metrics table with cascade delete
    CONSTRAINT fk_metric_age_range_metric
        FOREIGN KEY (metric_id)
        REFERENCES sdll_evaluation_metrics(id)
        ON DELETE CASCADE,

    -- Unique constraint: no duplicate age ranges for the same metric
    CONSTRAINT uq_metric_age_range
        UNIQUE KEY (metric_id, min_age, max_age),

    -- Index for quick lookups by metric
    INDEX idx_metric_id (metric_id)
);

-- Example: Add typical age ranges for a metric (uncomment to use)
-- INSERT INTO sdll_evaluation_metric_age_ranges (metric_id, min_age, max_age, min_score, max_score, score_increment)
-- VALUES
--     (1, 4, 6, 1.0, 3.0, 1.0),   -- T-Ball: simplified 1-3 scale
--     (1, 7, 9, 1.0, 5.0, 0.5),   -- Minors: 1-5 scale with half points
--     (1, 10, 12, 1.0, 7.0, 0.5); -- Majors: full 1-7 scale
