-- Add pitch_type column to sdll_leagues
-- Values: 'tee_ball', 'machine_pitch', 'kid_pitch'

ALTER TABLE `sdll_leagues`
ADD COLUMN `pitch_type` varchar(20) DEFAULT 'kid_pitch' AFTER `fall_display_name`;

-- Set initial pitch types
UPDATE `sdll_leagues` SET `pitch_type` = 'tee_ball'
WHERE `display_name` IN ('Tee Ball', 'Tee Ball BB', 'Tee Ball SB');

UPDATE `sdll_leagues` SET `pitch_type` = 'machine_pitch'
WHERE `display_name` IN ('BB Rookie', 'SB Rookie', 'BB A');

-- Everything else stays as default 'kid_pitch'
