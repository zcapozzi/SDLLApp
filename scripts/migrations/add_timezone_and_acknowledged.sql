-- Migration: Add timezone to organizations and acknowledged flag to game changes
-- Date: 2026-08-25
-- Purpose: Support local time display and pre-release change acknowledgment

-- Add timezone to organizations (default to America/New_York for existing)
ALTER TABLE sdll_organizations
ADD COLUMN timezone VARCHAR(50) DEFAULT 'America/New_York';

-- Add acknowledged flag to game changes (pre-release changes can be marked acknowledged)
ALTER TABLE sdll_game_changes
ADD COLUMN acknowledged TINYINT DEFAULT 0;

-- Add index for faster queries on non-acknowledged changes
ALTER TABLE sdll_game_changes
ADD INDEX idx_acknowledged (acknowledged);
