-- Migration: Drop deprecated league columns
-- These columns have been replaced by league_id FK
-- Run this AFTER deploying the code changes

-- Main tables - drop the deprecated string column
ALTER TABLE sdll_games DROP COLUMN league;
ALTER TABLE sdll_team_seasons DROP COLUMN league;
ALTER TABLE sdll_league_seasons DROP COLUMN league;
ALTER TABLE sdll_field_slots DROP COLUMN league;
ALTER TABLE sdll_field_allocations_specific DROP COLUMN league;
ALTER TABLE sdll_org_events DROP COLUMN league;

-- NOTE: The following tables KEEP their league columns for historical records:
-- - sdll_game_change_log (audit trail)
-- - sdll_umpire_dayof_notification (historical notifications)
-- - sdll_umpire_payment_event (payment history)
