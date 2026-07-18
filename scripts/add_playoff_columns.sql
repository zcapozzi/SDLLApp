-- Add playoff configuration columns

-- Number of teams that qualify for playoffs per league
ALTER TABLE `sdll_league_seasons`
ADD COLUMN `playoff_teams` int DEFAULT 4 AFTER `playoff_format`;

-- Add resolution tracking to team_seasons
-- seed_number: For "Seed 1", "Seed 2" placeholders (1, 2, 3, etc.)
-- bracket_position: For "Winner Game 1" type placeholders (e.g., "W1", "L1" for double elim)
-- resolved_team_id: The actual team that fills this placeholder once determined
ALTER TABLE `sdll_team_seasons`
ADD COLUMN `seed_number` int DEFAULT NULL AFTER `is_placeholder`,
ADD COLUMN `bracket_position` varchar(20) DEFAULT NULL AFTER `seed_number`,
ADD COLUMN `resolved_team_id` bigint DEFAULT NULL AFTER `bracket_position`;

-- Example playoff placeholder types:
-- Seed placeholders: is_placeholder=1, seed_number=1, display_name="Seed 1"
-- Bracket placeholders: is_placeholder=1, bracket_position="W1", display_name="Winner Game 1"
-- Once resolved: resolved_team_id points to the actual team
