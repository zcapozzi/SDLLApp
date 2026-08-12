-- Migration: Add regular_season_end_date and season_end_date to sdll_league_seasons
-- These dates enforce deadlines for regular season and playoff games

-- Add regular_season_end_date column (all regular season games must finish by this date)
ALTER TABLE sdll_league_seasons
ADD COLUMN IF NOT EXISTS regular_season_end_date DATE NULL;

-- Add season_end_date column (all playoff games must finish by this date)
ALTER TABLE sdll_league_seasons
ADD COLUMN IF NOT EXISTS season_end_date DATE NULL;

-- Verify columns were added
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'sdll_league_seasons'
  AND COLUMN_NAME IN ('regular_season_end_date', 'season_end_date');
