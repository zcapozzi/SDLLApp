-- Add league field rules columns to sdll_leagues
-- These define where each league can play games and practices

ALTER TABLE `sdll_leagues`
ADD COLUMN `allowed_game_fields` TEXT DEFAULT NULL COMMENT 'Comma-separated field IDs where league can play games (NULL = anywhere)',
ADD COLUMN `allowed_practice_fields` TEXT DEFAULT NULL COMMENT 'Comma-separated field IDs where league can practice (NULL = anywhere)',
ADD COLUMN `preferred_fields` TEXT DEFAULT NULL COMMENT 'Comma-separated field IDs in preference order',
ADD COLUMN `required_days` VARCHAR(50) DEFAULT NULL COMMENT 'Comma-separated day numbers (0=Mon, 6=Sun) when league must play';

-- Add field usage properties to sdll_fields
ALTER TABLE `sdll_fields`
ADD COLUMN `usage_type` VARCHAR(20) DEFAULT 'both' COMMENT 'both, games_only, practice_only',
ADD COLUMN `practice_capacity` INT DEFAULT 1 COMMENT 'How many teams can practice simultaneously',
ADD COLUMN `practice_capacity_late` INT DEFAULT NULL COMMENT 'Capacity for late slots (e.g., 7:30) if different';

-- Examples of what gets stored:
-- BB Majors: allowed_game_fields = '5' (Herndon only)
-- Intermediate: allowed_game_fields = '1,2,3,4,5' (Cedar Falls, Hillside, etc.)
-- Juniors: allowed_game_fields = '10,11' (Githens Baseball, Lowe's Grove)
-- Shepard: usage_type = 'practice_only'
-- Parkwood: practice_capacity = 2, practice_capacity_late = 1
