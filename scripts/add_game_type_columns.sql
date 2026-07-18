-- Add game_type column to sdll_games
-- Values: 'regular', 'playoff', 'practice'
ALTER TABLE `sdll_games`
ADD COLUMN `game_type` varchar(20) DEFAULT 'regular' AFTER `is_spring`;

-- Add regular_season_games to sdll_league_seasons
-- Number of games each team plays in regular season
ALTER TABLE `sdll_league_seasons`
ADD COLUMN `regular_season_games` int DEFAULT 10 AFTER `playoff_teams`;

-- Update existing games to have game_type based on is_scrimmage
UPDATE `sdll_games` SET `game_type` = 'practice' WHERE `is_scrimmage` = 1;
