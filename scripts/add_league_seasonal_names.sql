-- Add fall_display_name column to sdll_leagues
-- If set, this name is used for Fall seasons; display_name is used for Spring
-- If NULL, display_name is used for both seasons

ALTER TABLE `sdll_leagues`
ADD COLUMN `fall_display_name` varchar(100) DEFAULT NULL AFTER `display_name`;

-- Set Fall names for leagues that use different names
UPDATE `sdll_leagues` SET `fall_display_name` = 'BB Cactus' WHERE `display_name` = 'BB AA';
UPDATE `sdll_leagues` SET `fall_display_name` = 'BB Grapefruit' WHERE `display_name` = 'BB AAA';

-- The display_name column now represents the Spring/canonical name
-- Examples:
--   display_name='BB AA', fall_display_name='BB Cactus'
--   display_name='BB AAA', fall_display_name='BB Grapefruit'
--   display_name='BB Majors', fall_display_name=NULL (same name both seasons)
