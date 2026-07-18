-- Add schedule settings to sdll_league_seasons
-- Day types: NULL/empty = nothing, 'practice', 'game'

ALTER TABLE `sdll_league_seasons`
ADD COLUMN `monday_type` varchar(10) DEFAULT NULL AFTER `notes`,
ADD COLUMN `tuesday_type` varchar(10) DEFAULT NULL AFTER `monday_type`,
ADD COLUMN `wednesday_type` varchar(10) DEFAULT NULL AFTER `tuesday_type`,
ADD COLUMN `thursday_type` varchar(10) DEFAULT NULL AFTER `wednesday_type`,
ADD COLUMN `friday_type` varchar(10) DEFAULT NULL AFTER `thursday_type`,
ADD COLUMN `saturday_type` varchar(10) DEFAULT NULL AFTER `friday_type`,
ADD COLUMN `sunday_type` varchar(10) DEFAULT NULL AFTER `saturday_type`,
ADD COLUMN `first_practice_date` date DEFAULT NULL AFTER `sunday_type`,
ADD COLUMN `opening_day_date` date DEFAULT NULL AFTER `first_practice_date`;

-- Examples:
-- BB Majors: Games on Mon/Wed, Practice on Tue/Thu
--   monday_type='game', tuesday_type='practice', wednesday_type='game', thursday_type='practice'
-- Tee Ball: Practice on Sat morning, Games on Sat afternoon (both would be on same day)
--   saturday_type='game' (or 'practice' depending on primary use)
