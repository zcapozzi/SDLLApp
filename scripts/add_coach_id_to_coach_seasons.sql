-- Add coach_id column to sdll_coach_seasons to link to sdll_coaches
-- Run this migration on your database

ALTER TABLE sdll_coach_seasons
ADD COLUMN coach_id BIGINT NULL AFTER team_id;

-- Add foreign key constraint
ALTER TABLE sdll_coach_seasons
ADD CONSTRAINT fk_coach_seasons_coach
FOREIGN KEY (coach_id) REFERENCES sdll_coaches(id) ON DELETE SET NULL;

-- Add index for faster lookups
CREATE INDEX idx_coach_seasons_coach_id ON sdll_coach_seasons(coach_id);
