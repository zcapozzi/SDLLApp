-- Migration: Add schedule_token column to sdll_league_seasons for public division schedule access
-- Run: mysql -u lrp_master -p sdll_test < scripts/add_division_schedule_token.sql

ALTER TABLE sdll_league_seasons
ADD COLUMN schedule_token VARCHAR(32) UNIQUE DEFAULT NULL;

-- Add index for fast token lookups
CREATE INDEX idx_league_seasons_schedule_token ON sdll_league_seasons(schedule_token);
