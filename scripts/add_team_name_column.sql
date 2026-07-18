-- Add team_name column to sdll_team_seasons
-- team_name stores the chosen name (e.g., "Thunderbolts")
-- display_name stores the placeholder (e.g., "BB Majors Team 1")

ALTER TABLE `sdll_team_seasons`
ADD COLUMN `team_name` varchar(50) DEFAULT NULL AFTER `display_name`;
