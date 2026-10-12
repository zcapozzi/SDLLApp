-- Drop legacy metric columns from sdll_player_evaluations
-- These are now stored in sdll_player_evaluation_scores via flexible metrics
--
-- Run with: mysql --force database < script.sql
-- (--force continues on errors if columns don't exist)

-- Drop individual metric columns
ALTER TABLE sdll_player_evaluations DROP COLUMN contact;
ALTER TABLE sdll_player_evaluations DROP COLUMN power;
ALTER TABLE sdll_player_evaluations DROP COLUMN glove;
ALTER TABLE sdll_player_evaluations DROP COLUMN arm;
ALTER TABLE sdll_player_evaluations DROP COLUMN outfield;
ALTER TABLE sdll_player_evaluations DROP COLUMN control;
ALTER TABLE sdll_player_evaluations DROP COLUMN velocity;
ALTER TABLE sdll_player_evaluations DROP COLUMN speed;

-- Rename avg_score to overall_score for clarity (if it exists)
ALTER TABLE sdll_player_evaluations CHANGE COLUMN avg_score overall_score DECIMAL(3,2);

-- If avg_score doesn't exist but overall_score column is needed, add it:
-- ALTER TABLE sdll_player_evaluations ADD COLUMN overall_score DECIMAL(3,2);
