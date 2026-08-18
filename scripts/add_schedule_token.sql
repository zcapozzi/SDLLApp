-- Add schedule_token column to sdll_team_seasons for public schedule URLs
-- This allows each team to have a unique, shareable URL for their schedule

ALTER TABLE `sdll_team_seasons`
ADD COLUMN `schedule_token` VARCHAR(32) DEFAULT NULL COMMENT 'Unique token for public schedule URL',
ADD UNIQUE INDEX `idx_schedule_token` (`schedule_token`);

-- Generate tokens for existing teams (Fall 2026)
-- Run this after the column is added:
-- UPDATE sdll_team_seasons
-- SET schedule_token = SUBSTRING(MD5(RAND()), 1, 16)
-- WHERE schedule_token IS NULL AND active = 1;
