-- Add time restriction columns to sdll_leagues
-- earliest_start_time: League games cannot start before this time (NULL = no restriction)
-- latest_start_time: League games cannot start after this time (NULL = no restriction)

ALTER TABLE `sdll_leagues`
ADD COLUMN `earliest_start_time` time DEFAULT NULL AFTER `only_assignr_groups`,
ADD COLUMN `latest_start_time` time DEFAULT NULL AFTER `earliest_start_time`;

-- Set initial restrictions for younger leagues (cannot play after 5:30 PM)
UPDATE `sdll_leagues` SET `latest_start_time` = '17:30:00'
WHERE `display_name` IN ('Tee Ball', 'Tee Ball BB', 'Tee Ball SB', 'BB Rookie', 'SB Rookie', 'BB A');

-- Examples:
-- No restrictions: earliest_start_time=NULL, latest_start_time=NULL
-- Young kids (before 5:30): earliest_start_time=NULL, latest_start_time='17:30:00'
-- Evening only (6pm+): earliest_start_time='18:00:00', latest_start_time=NULL
-- Specific window: earliest_start_time='17:00:00', latest_start_time='19:30:00'
