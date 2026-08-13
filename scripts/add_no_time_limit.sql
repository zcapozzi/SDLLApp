-- Add no_time_limit flag to sdll_games table
-- No-time-limit games are allocated 3 hours instead of 2 hours
-- This flag helps umpires know the game format

ALTER TABLE sdll_games
ADD COLUMN no_time_limit TINYINT DEFAULT 0
AFTER is_scrimmage;

-- Verify the column was added
DESCRIBE sdll_games;
