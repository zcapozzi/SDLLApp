-- Add has_scrimmages to league_seasons (some leagues don't have scrimmages)
ALTER TABLE sdll_league_seasons
ADD COLUMN has_scrimmages TINYINT(1) NOT NULL DEFAULT 1;

-- Add practice_days to team_seasons (team-specific override of league practice days)
-- NULL means use the league default
ALTER TABLE sdll_team_seasons
ADD COLUMN practice_days VARCHAR(50) DEFAULT NULL;

-- Add is_league_practice flag for group practices where all teams practice together
ALTER TABLE sdll_games
ADD COLUMN is_league_practice TINYINT(1) NOT NULL DEFAULT 0;

-- Set has_scrimmages to FALSE for tee ball and rookie leagues
UPDATE sdll_league_seasons
SET has_scrimmages = 0
WHERE league IN ('BB Tee Ball', 'SB Tee Ball', 'BB Rookie');
