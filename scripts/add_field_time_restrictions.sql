-- Add game time restriction columns to sdll_fields
-- These restrict when GAMES can be scheduled (practices are not affected)

ALTER TABLE sdll_fields ADD COLUMN game_earliest_weekday TIME DEFAULT NULL;
ALTER TABLE sdll_fields ADD COLUMN game_latest_weekday TIME DEFAULT NULL;
ALTER TABLE sdll_fields ADD COLUMN game_earliest_weekend TIME DEFAULT NULL;
ALTER TABLE sdll_fields ADD COLUMN game_latest_weekend TIME DEFAULT NULL;

-- Example: Set Cedar Falls to only allow games 6:30 PM - 8:30 PM on weekdays
-- UPDATE sdll_fields SET game_earliest_weekday = '18:30:00', game_latest_weekday = '20:30:00' WHERE location_title = 'Cedar Falls';

-- Verify the changes
SELECT ID, location_title, game_earliest_weekday, game_latest_weekday, game_earliest_weekend, game_latest_weekend
FROM sdll_fields
WHERE active = 1
ORDER BY location_title;
