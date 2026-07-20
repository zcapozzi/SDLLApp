-- Add sort_order column to sdll_leagues for controlling display order
-- Lower numbers sort first (youngest kids to oldest)

ALTER TABLE sdll_leagues ADD COLUMN sort_order INT DEFAULT 100;

-- Set sort order for Baseball leagues (youngest to oldest)
UPDATE sdll_leagues SET sort_order = 10 WHERE display_name = 'BB Tee Ball';
UPDATE sdll_leagues SET sort_order = 20 WHERE display_name = 'BB Rookie';
UPDATE sdll_leagues SET sort_order = 30 WHERE display_name = 'BB A';
UPDATE sdll_leagues SET sort_order = 40 WHERE display_name = 'BB AA';
UPDATE sdll_leagues SET sort_order = 50 WHERE display_name = 'BB AAA';
UPDATE sdll_leagues SET sort_order = 60 WHERE display_name = 'BB Majors';
UPDATE sdll_leagues SET sort_order = 70 WHERE display_name = 'BB Intermediate';
UPDATE sdll_leagues SET sort_order = 80 WHERE display_name = 'BB Juniors';

-- Set sort order for Softball leagues (youngest to oldest)
UPDATE sdll_leagues SET sort_order = 110 WHERE display_name = 'SB Tee Ball';
UPDATE sdll_leagues SET sort_order = 120 WHERE display_name = 'SB Rookie';
UPDATE sdll_leagues SET sort_order = 130 WHERE display_name = 'SB Minors';
UPDATE sdll_leagues SET sort_order = 140 WHERE display_name = 'SB Majors';
UPDATE sdll_leagues SET sort_order = 150 WHERE display_name = 'SB Seniors';

-- Verify the results
SELECT ID, display_name, sort_order FROM sdll_leagues WHERE active = 1 ORDER BY sort_order, display_name;
