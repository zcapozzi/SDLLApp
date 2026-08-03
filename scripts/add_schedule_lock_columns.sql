-- Migration: Add schedule lock columns to sdll_league_seasons
-- These columns support the three-phase scheduling workflow:
-- Phase 1 (Setup): Create empty game slots
-- Phase 2 (Draft): Fill in matchups/dates/fields (can regenerate)
-- Phase 3 (Locked): Schedule accepted, manual edits only

ALTER TABLE sdll_league_seasons
ADD COLUMN schedule_locked TINYINT(1) DEFAULT 0 COMMENT 'Whether schedule is locked (Phase 3)';

ALTER TABLE sdll_league_seasons
ADD COLUMN schedule_locked_at DATETIME NULL COMMENT 'When the schedule was locked';

ALTER TABLE sdll_league_seasons
ADD COLUMN schedule_locked_by BIGINT NULL COMMENT 'User ID who locked the schedule';

-- Verify the changes
DESCRIBE sdll_league_seasons;
