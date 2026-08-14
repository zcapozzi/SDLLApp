-- Add game and practice duration columns to sdll_leagues
-- Tee Ball leagues use 75 minutes, others use 120 minutes for games, 90 minutes for practices

ALTER TABLE sdll_leagues
ADD COLUMN game_duration_minutes INT DEFAULT NULL COMMENT 'Game duration in minutes. NULL = use default (120 for regular, 180 for no-time-limit)',
ADD COLUMN practice_duration_minutes INT DEFAULT NULL COMMENT 'Practice duration in minutes. NULL = use default (90)';

-- Set Tee Ball leagues to 75 minutes for both games and practices
UPDATE sdll_leagues
SET game_duration_minutes = 75, practice_duration_minutes = 75
WHERE display_name LIKE '%Tee Ball%';

-- Verify the update
SELECT ID, display_name, game_duration_minutes, practice_duration_minutes
FROM sdll_leagues
WHERE active = 1
ORDER BY sort_order;
