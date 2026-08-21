-- Add coach_name column to sdll_team_seasons table
-- This column stores the coach name for scheduler/admin views
-- For production, the user already added this column directly

-- Check if column exists before adding (MySQL-compatible approach)
-- If this fails because column already exists, that's OK

ALTER TABLE sdll_team_seasons ADD COLUMN coach_name VARCHAR(100) DEFAULT NULL;
