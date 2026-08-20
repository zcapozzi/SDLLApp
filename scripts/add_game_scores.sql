-- Add home_score and away_score columns to sdll_games table
-- These are only populated for completed regular/playoff games (not scrimmages)

ALTER TABLE sdll_games
ADD COLUMN home_score SMALLINT DEFAULT NULL COMMENT 'Home team score (regular/playoff games only)',
ADD COLUMN away_score SMALLINT DEFAULT NULL COMMENT 'Away team score (regular/playoff games only)';

-- Verify the columns were added
SELECT 'Columns added successfully' AS status;
DESCRIBE sdll_games;
