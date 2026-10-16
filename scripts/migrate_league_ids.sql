-- Migration: Convert league string columns to league_id foreign keys
-- Run this script against the production database AFTER deploying the code changes

-- 1. GameChange: Add league_id column and populate from league_name lookup
ALTER TABLE sdll_game_changes ADD COLUMN league_id BIGINT;

-- Populate league_id from existing league string values
UPDATE sdll_game_changes gc
JOIN sdll_leagues l ON gc.league = l.display_name
SET gc.league_id = l.ID
WHERE gc.league IS NOT NULL;

-- Add foreign key constraint
ALTER TABLE sdll_game_changes
ADD CONSTRAINT fk_game_changes_league
FOREIGN KEY (league_id) REFERENCES sdll_leagues(ID);

-- Drop the old league column (only after verifying data migration worked)
-- ALTER TABLE sdll_game_changes DROP COLUMN league;


-- 2. UmpireDayOfNotification: Add game_league_id column
ALTER TABLE sdll_umpire_dayof_notifications ADD COLUMN game_league_id BIGINT;

-- Populate from existing game_league string values
UPDATE sdll_umpire_dayof_notifications n
JOIN sdll_leagues l ON n.game_league = l.display_name
SET n.game_league_id = l.ID
WHERE n.game_league IS NOT NULL;

-- Add foreign key constraint
ALTER TABLE sdll_umpire_dayof_notifications
ADD CONSTRAINT fk_dayof_notifications_league
FOREIGN KEY (game_league_id) REFERENCES sdll_leagues(ID);

-- Drop the old column (only after verifying data migration worked)
-- ALTER TABLE sdll_umpire_dayof_notifications DROP COLUMN game_league;


-- 3. UmpirePaymentEvent: Add original_league_id column
ALTER TABLE sdll_umpire_payment_events ADD COLUMN original_league_id BIGINT;

-- Populate from existing original_league string values
UPDATE sdll_umpire_payment_events pe
JOIN sdll_leagues l ON pe.original_league = l.display_name
SET pe.original_league_id = l.ID
WHERE pe.original_league IS NOT NULL;

-- Add foreign key constraint
ALTER TABLE sdll_umpire_payment_events
ADD CONSTRAINT fk_payment_events_league
FOREIGN KEY (original_league_id) REFERENCES sdll_leagues(ID);

-- Drop the old column (only after verifying data migration worked)
-- ALTER TABLE sdll_umpire_payment_events DROP COLUMN original_league;


-- Verification queries - run these to ensure migration worked:
-- SELECT COUNT(*) as total, COUNT(league_id) as with_league_id FROM sdll_game_changes WHERE league IS NOT NULL;
-- SELECT COUNT(*) as total, COUNT(game_league_id) as with_league_id FROM sdll_umpire_dayof_notifications WHERE game_league IS NOT NULL;
-- SELECT COUNT(*) as total, COUNT(original_league_id) as with_league_id FROM sdll_umpire_payment_events WHERE original_league IS NOT NULL;
