-- Migration to add ramp-up schedule fields to sdll_league_seasons
-- Allows configuring reduced games/practices during first weeks of season
--
-- Usage: Run with --force to continue on errors (in case columns already exist)
--   mysql --force database < scripts/add_ramp_up_schedule.sql
--
-- NOTE: Using plain ALTER TABLE syntax for MySQL compatibility (not MariaDB-only IF NOT EXISTS)

-- How many weeks at the start to use reduced schedule (0 = no ramp-up)
ALTER TABLE sdll_league_seasons
ADD COLUMN ramp_up_weeks INT DEFAULT 0;

-- Max games per team per week during ramp-up period (typically 1)
ALTER TABLE sdll_league_seasons
ADD COLUMN ramp_up_games_per_week INT DEFAULT 1;

-- Max games per team per week after ramp-up (typically 2)
ALTER TABLE sdll_league_seasons
ADD COLUMN full_schedule_games_per_week INT DEFAULT 2;

-- Max practices per team per week during ramp-up (typically 2)
ALTER TABLE sdll_league_seasons
ADD COLUMN ramp_up_practices_per_week INT DEFAULT 2;

-- Max practices per team per week after ramp-up (typically 1)
ALTER TABLE sdll_league_seasons
ADD COLUMN full_schedule_practices_per_week INT DEFAULT 1;

-- Done
SELECT 'Ramp-up schedule columns added to sdll_league_seasons' AS status;
